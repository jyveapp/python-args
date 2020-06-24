.. _tutorial:

Tutorial
========

``python-args`` installs the ``arg`` module and comes with three main
decorators:

1. ``@arg.validators`` - Run validators against function arguments.
2. ``@arg.defaults`` - Process and coerce default values for arguments.
3. ``@arg.contexts`` - Run context managers around functions using arguments.
4. ``@arg.parametrize`` - For parametrizing an argument of a function.

``python-args`` provides several utilities for lazily-evaluating code within
the decorators:

1. ``arg.func`` - Run a lazy function.
2. ``arg.init`` - Lazily initialize a class.
3. ``arg.val`` - A shortcut to return the value of an argument to a function.
4. ``arg.first`` - A shortcut to return the value of the first loadable lazy
   object.

As we will discuss later, the combination of these utilities offers the
ability to construct functions in a more digestible and testable manner.

We will cover these decorators and lazy utilities in the following, along with
covering some additional features such as ``arg.s``. We start
off with `@arg.validators <arg.validators>`.

Using ``@arg.validators``
-------------------------

A common design when writing python functions is validating the
parameters to a function. For example, consider the following function
that sends an email to an address:

.. code-block:: python

  def send_email(email_address, message):
      if not _validate_email(email_address):
          raise ValueError(f'Email address "{email_address}" is invalid.')

      if not message:
          raise ValueError('Must provide message')

      # Contact the SMTP server to send the email.
      _send_email(email_address, message)

      # Create a record that the email was sent
      EmailRecord.objects.create(email_address, message)


In this example, we:

1. Check that a valid email address was supplied.
2. Ensure the user passed a message that wasn't empty.
3. Call the actual code to do the request that sends the email.
4. Create a record in our database about the email being successfully
   sent (we are using Django in this example, but that's not important).

When writing code in this way, it is more difficult to construct unit tests
for some of the core business logic of the ``send_email`` function. For
example, in order to test that we are creating an appropriate email record
when we send an email, we have to be sure to set up the proper state so
that our validations hold true (or mock out the validations).

For this particular example, this may be trivial, but the problem can
easily grow in complexity when validating arguments against database state
or other conditions.

Enter `@arg.validators <arg.validators>`. The `validators` decorator allows you
to construct a function and apply validators to appropriate arguments.
Let's take the previous example:


.. code-block:: python

  import arg


  def validate_email(email_address):
    if not _validate_email(email_address):
        raise ValueError(f'Email address "{email_address}" is invalid.')

  def validate_message(message):
    if not message:
        raise ValueError('Must provide message')

  @arg.validators(validate_email, validate_message)
  def send_email(email_address, message):
      message = message.strip()
      email_address = email_address.lower()

      with transaction.atomic():
          # Create a record that we sent the email
          EmailRecord.objects.create(email_address, message)

          # Hit our email server and send it. If an error happens,
          # our transaction will be rolled back and we won't store the record
          send_email_via_smtp(email_address, message)


The function above has the same behavior as calling:

.. code-block:: python

  def send_email(email_address, message):
      validate_email(email_address)
      validate_message(message)

      message = message.strip()
      email_address = email_address.lower()

      with transaction.atomic():
        ...

``python-args`` knows how to orchestrate this by inspecting the argument
names to the original function and calling validators with matching
argument names.

.. note::

    Validators can take any subset of the arguments of the calling function
    based on the argument names. If the argument names don't match, keep
    reading about `@arg.defaults <arg.defaults>` later for ways around this.

When structuring your code with `@arg.validators <arg.validators>`,
you get the following:

1. Validation functions that are completely separate and can be tested
   in isolation.
2. The ability to run only the validators of your function. Using our
   example above, one can call ``send_email.pre_func(email_address, message)``
   to run all code that is executed before the main function (in this case,
   the validators).
3. The ability to run the function without validators. Using our
   example above, one can call ``send_email.func(email_address, message)``
   to only run the wrapped function.

With these characteristics in mind, one now has more tools at their disposal
for constructing unit tests that focus on core business logic instead of
setting up state (or mocking it out).

Along with this, higher-level tools can more seamlessly integrate with
``python-args`` functions. For example, it is possible to integrate the
validators of this function with a Django form that calls the function
with user-supplied arguments, all while keeping the validation close to
the core logic.

.. note::

  ``python-args`` currently only supports validators that throw exceptions
  when failing. We are considering some extensions that allow validators
  that return ``bool`` values.

Using ``@arg.defaults``
-----------------------

Similar to validators, another common pattern is to process the default
value for an argument into something usable for the function. For example,
consider the classic case of avoiding using mutable keyword argument
defaults:

.. code-block:: python

  def my_kwarg_func(my_kwarg=None):
      my_kwarg = my_kwarg or []
      ...

Another common use case is stripping string values:

.. code-block:: python

  def my_str_func(str_arg):
      str_arg = str_arg.strip()
      ...

The `@arg.defaults <arg.defaults>` decorator allows one to apply default
processing to arguments before the function is called. Let's take our
two examples above and convert them to use `@arg.defaults <arg.defaults>`:

.. code-block:: python

  @arg.defaults(my_kwarg=lambda: my_kwarg or [])
  def my_kwarg_func(my_kwarg=None)
      ...


  @arg.defaults(str_arg=lambda: str_arg.strip())
  def my_str_func(str_arg):
      ...

`@arg.defaults <arg.defaults>` takes the argument name and its associated logic
for processing it. Although we are using a ``lambda`` here,
`@arg.defaults <arg.defaults>` values can take functions and other lazy
utilities offered by ``python-args`` (more on this later).

Similar to `@arg.validators <arg.validators>`, the same principles apply here -
One can write and test default processors more elegantly in isolation while
keeping focus on core business logic.

`@arg.defaults <arg.defaults>` also allows us to preprocess default values
before validators run. For example, take our previous example using
`@arg.validators <arg.validators>`:

.. code-block:: python

  @arg.validators(validate_email, validate_message)
  def send_email(email_address, message):
      message = message.strip()
      email_address = email_address.lower()

      ...

In the above, the ``validate_email`` and ``validate_message`` validators
also have to preprocess the arguments before running validation. This can
be solved with stacking the decorators in the order in which they should
be applied:

.. code-block:: python

  @arg.defaults(email_address=lambda email_address: email_address.lower(),
                message=lambda message: message.strip())
  @arg.validators(validate_email, validate_message)
  def send_email(email_address, message):
      ...


Using ``@arg.contexts``
-----------------------

Sometimes resources need to be created before a function and destroyed after
its execution or instrumentation needs to be put in place. Context managers
are the preferred python design pattern for this, and ``python-args``
comes with the `@arg.contexts <arg.contexts>` decorator to enter and leave
context managers.

For example, the following context manager logs a message before and
after execution:

.. code-block:: python

  import contextlib
  import logging

  import args


  @contextlib.contextmanager
  def log_func():
      logging.info('Starting')
      yield
      logging.info('Finishing')


  @arg.contexts(log_func)
  def my_func(arg):
      ...

Similar to other ``python-args`` decorators, context managers can take named
arguments that are named the same as the underlying function.

Need to attach a value from a context manager to an argument name before
the execution of the function? Similar to `@arg.defaults <arg.defaults>`,
`@arg.contexts <arg.contexts>` can re-assign the argument before
execution.

For example, consider the pattern of a function that can either take
in a file name or an already-open file object:


.. code-block:: python

  import os

  def read_file_contents(file_obj):
      """Read the file contents of the file object.

      If the file object is a string, open the file and read it.
      """
      if isinstance(file_obj, str):
          with open(file_obj, 'r') as f:
              return f.read()
      else:
          return f.read()


By using `@arg.contexts <arg.contexts>` with a label for the context manager,
the result of the context manager will be used for the argument. For example,


.. code-block:: python

  import os


  @contextlib.contextmanager
  def ensure_file_obj(file_obj):
      if isinstance(file_obj, str):
          with open(file_obj, 'r') as file_obj:
              yield file_obj
      else:
          yield file_obj


  @arg.contexts(file_obj=ensure_file_obj)
  def read_file_contents(file_obj):
      return f.read()

With this pattern, the ``ensure_file_obj`` context manager can be re-used
for this particularly ugly scenario of handling a file name or file-like object.

Using ``@arg.parametrize``
--------------------------

Similar to the parametrization in
`pytest <https://docs.pytest.org/en/latest/>`__, ``python-args`` allows
one to parametrize the input to a function using
`@arg.parametrize <arg.parametrize>`. Here's an example of a function
that doubles a number and an associated parametrization:

.. code-block:: python

    @arg.parametrize(number=arg.val('numbers'))
    def double(number):
        return val * 2

    assert double(numbers=[1, 3, 4, 5]) == [2, 6, 8, 10]

Similar to `@arg.defaults <arg.defaults>`, `@arg.parametrize <arg.parametrize>`
can bind an argument from another value. In the case of
`@arg.parametrize <arg.parametrize>`, the value must be an iterable.

When used, the resulting function returns a list of all parametrized
results.

.. note::

  `@arg.parametrize <arg.parametrize>` can only parametrize one argument
  at a time. Nesting `@arg.parametrize <arg.parametrize>` will result
  in a list that contains other lists.


Accessing properties of the current call
----------------------------------------

Each run of a function decorated with ``python-args`` stores global
state about the current call. This information can be gathered with
`arg.call` and can be called inside of any function supplied to the
primary ``python-args`` decorators.

Below is a code example of a context manager that is used as
a ``python-args`` context. The docs for the code elaborate on what
various properties mean.


.. code-block:: python

    import arg

    @contextlib.context
    def my_args_context():
        # Get the current python-args call. This will raise an error if
        # called outside of a python-args function
        c = arg.call()

        # When this flag is true, we are running in partial mode and
        # are only running python-args decorators that can be bound
        # to the calling arguments
        c.is_partial

        # When this flag is true, we are running in pre_func mode.
        # This means we are only running everything up to the main function.
        # Sometimes context managers might want to use this mode to
        # alter their run-time characteristics
        c.is_pre_func

        # All of these arguments are set when running under a parametrization
        # of an argument.
        c.parametrized_arg  # The argument name being parametrized
        c.parametrized_arg_val  # The value of the argument
        c.parametrized_arg_index  # The index with respect to all values
        c.parametrized_arg_vals  # All values that are being parametrized


    @arg.contexts(my_args_context)
    def my_args_func():
        ...


Arg naming limitations and work-arounds
---------------------------------------

``python-args`` decorators work well when argument names are consistent.
As long as argument names match in contexts, validators, and defaults,
things will work as expected. However, in order to more easily share contexts,
validators, and defaults among code, it does require that all code uses the
same argument names. When argument names do not match, a lazy binding error
will be raised when calling the decorated function.

This is a known limitation. Here we offer a few work-arounds and some future
plans for easing this burden.

For now, stacking `@arg.defaults <arg.defaults>` is the best way to ensure
that argument names match. For example, let's use our ``ensure_file_obj``
context manager from before that uses a ``file_obj`` argument. In the
following example, we declare a function that should take a file object, but
the argument is not named ``file_obj``:

.. code-block:: python

    def parse_file(my_file):
      # Do file parsing on the file object.


In order to take advantage of our previously-declared ``ensure_file_obj``
context, we need to process the default values before passing them into
the context:

.. code-block:: python

    @arg.defaults(file_obj=lambda my_file: my_file)
    @arg.contexts(my_file=ensure_file_obj)
    def parse_file(my_file):
        # Do file parsing. my_file will be a file object

In the above, the ``file_obj`` argument is created from the ``my_file``
argument and passed down through the chain. Since the ``ensure_file_obj``
expects a ``file_obj`` argument, it will succeed and assign the proper
value to the ``my_file`` argument before it is passed to ``parse_file``.

Although it is possible to create argument processing chains like this, it
is not recommended for the sake of readability. ``python-args`` plans to
address the obvious limitation in future releases by allowing one to more
clearly specify how validators, contexts, and defaults can be called
from arguments that don't have matching argument names.

``python-args`` has some shortcuts for lazy loading to
help reduce the boilerplate of writing ``lambda`` functions.
We cover these in the next section.

Args lazy-loading shortcuts
---------------------------

For simple `@arg.defaults <arg.defaults>` processing or more digestible
argument renaming, ``python-args`` comes with a few utilities to help
the user avoid writing ``lambda`` expressions or declaring new functions for
trivial operations.

Using ``arg.val``
~~~~~~~~~~~~~~~~~

`arg.val` is used to retrieve the value of an argument. For example,

.. code-block:: python

  @arg.defaults(arg1=lambda other_arg: other_arg)
  def my_func(arg1):
      ...

The above assigns the ``arg1`` argument the value of ``other_arg`` when
``my_func`` is called with ``other_arg``. This expression can be
shortened with:

.. code-block:: python

  @arg.defaults(arg1=arg.val('other_arg'))
  def my_func(arg1):
      ...

`arg.val` can be chained. Let's go back to a previous example where we
ensure that a string message is stripped before executing a function:

.. code-block:: python

  @arg.defaults(my_str_arg=arg.val('my_str_arg').strip())
  def my_func(my_str_arg):
      ...

Using ``arg.init``
~~~~~~~~~~~~~~~~~~

`arg.init` is a shortcut to initialize a class. Instead of:

.. code-block:: python

  @arg.defaults(arg1=lambda: MyClass(kwarg=arg1))
  def my_func(arg1):
      ...

One can use `arg.init`:

.. code-block:: python

  @arg.defaults(arg1=arg.init(MyClass, kwarg=arg.val('arg1')))
  def my_func(arg1):
      ...

Similar to `arg.val`, `arg.init` calls can be chained.

Using ``arg.func``
~~~~~~~~~~~~~~~~~~

All functions passed to `@arg.defaults <arg.defaults>`,
`@arg.validators <arg.validators>`, and `@arg.contexts <arg.contexts>`
are wrapped in an `arg.func` call. `arg.func` takes a function and
lazily binds arguments to it. This is how ``python-args`` is able to
dynamically bind function arguments to the various decorators.
Although it is not necessary to use this utility with any
current ``python-args`` decorators, users are able to inherit `arg.func`
and create other lazy utilities to use with ``python-args`` decorators.

Using ``arg.first``
~~~~~~~~~~~~~~~~~~~

`arg.first` is a shortcut to obtain the first value that can be lazily
loaded. It takes an arbitrary amount of lazy objects (such as `arg.val`
or `arg.func`). For example:

.. code-block:: python

  @arg.defaults(arg1=arg.first(arg.val('b'), arg.val('c')))
  def my_func(arg1):
      return arg1

  assert my_func(b=1, c=3) == 1
  assert my_func(c=3) == 3

Similar to `arg.val`, a ``default`` keyword argument can be used to
return a default value if no arguments can be binded.
Users may also pass in strings as a shorthand
for `arg.val` or callables as a shorthand for `arg.func`. For example,
this is equivalent to our previous example:

.. code-block:: python

  @arg.defaults(arg1=arg.first('b', 'c'))
  def my_func(arg1):
      return arg1

Partial and pre_func run modes
------------------------------

As briefly described earlier, ``python-args`` allows decorated functions
to be executed in various modes. One mode, the ``pre_func`` mode, ensures
that only the code before the primary function is executed. This allows
other tools to seamlessly only run validators and other pre-processing
logic without running the underlying function. As mentioned earlier,
this interface is accessed with the ``pre_func`` attribute on the decorated
function.

Along with the ``pre_func`` mode, ``python-args`` can also go a step further
and only run ``pre_func`` routines based on the arguments provided. This is done
with the ``partial`` attribute of the decorated function.

Partially running the ``pre_func`` routines of the decorated function allows
us to verify that individual arguments are in good shape before running
the function.

For example, imagine one is writing a command line interface for a function
and wishes to individually validate arguments and provide useful error
messages. Assuming the function
is called ``my_func``, this can be done by calling
``my_func.pre_func.partial(arg_name=value)`` to only run the ``pre_func``
routines associated with ``arg_name``.

Creating aggregate decorators with ``arg.s``
--------------------------------------------

``python-args`` decorators such as `@arg.validators <arg.validators>`
`@arg.contexts <arg.contexts>` are meant to be stacked on top of one
another to create chains of processing for arguments. However,
repeating the same chains of decorators across similar functions
can become unwieldy over time.

The `arg.s` utility can be used to address this and combine chains into
one single decorator. For example, let's say that you have a function decorated
like so:

.. code-block:: python

  @arg.validators(validate_object)
  @arg.contexts(track_object_changes, trap_errors)
  def my_func(...):
      ...

If this pattern needs to be applied to many functions, it can be useful
to make a single decorator. This is where `arg.s` comes in handy:

.. code-block:: python

    validate_object_and_track_changes = arg.s(
        arg.validators(validate_object),
        arg.contexts(track_object_changes, trap_errors),
    )

    @validate_object_and_track_changes
    def my_func(...):
        ...

.. note::

    One can similarly use ``validate_object_and_track_changes`` as a
    function runner or orchestrator by calling
    ``validate_object_and_track_changes(function_to_run)``.
