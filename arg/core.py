"""
The core interface and constructs for python-args.
"""
import contextlib
import inspect
import threading


# A sentinel value to know if a default value of a kwarg was provided.
_unset = object()

# The current python-args call being executed.
# Allows us to set run-time parameters and maintain additional information
# about the call.
# TODO: Make this a local variable that is passed through the call chain
_current_call = threading.local()


class Call:
    """Contains information about an executing python-args call.

    Values can only be set temporarily using set()
    """

    def __init__(self):
        # True if we are running partial mode. Partial mode allows
        # us to only run python-arg decorators that can be bound
        # to the current arguments.
        self.is_partial = False

        # True if we are running pre_func mode. The pre_func mode
        # will make python-args run everything up until the actual
        # wrapped function.
        self.is_pre_func = False

        # These arguments are set during parametrization to give the
        # user access to the current parametrized arg name, the current
        # value, the index of the value with respect to all values, and
        # all arg values that are being parametrized
        self.parametrize_arg = None
        self.parametrize_arg_val = None
        self.parametrize_arg_index = None
        self.parametrize_arg_vals = None

    def set(self, **kwargs):
        """Temporarily set attributes of the call"""

        @contextlib.contextmanager
        def temporary_set():
            orig = {key: getattr(self, key) for key in kwargs}
            for key, value in kwargs.items():
                setattr(self, key, value)

            yield

            for key, value in orig.items():
                setattr(self, key, value)

        return temporary_set()


def call():
    """Obtains the current python-args call

    The current call is always set by the __call__ method of
    the Args class when invoking running.
    """
    if not hasattr(_current_call, 'val'):
        raise AssertionError('No python-args function is running.')

    return _current_call.val


class BindError(TypeError):
    """When a function can't be bound to arguments

    For example, if @args.defaults or @args.validators
    have functions that take arguments with names other than
    the function they are decorating, a BindError
    could be thrown if the called function does not have all
    necessary arguments.
    """


def _parse_args(func, args=None, kwargs=None, extra=False, partial=False):
    """
    Parses the arguments to the function and returns a dictionary of
    arguments.

    Args:
        func (function): The function over which arguments are parsed.
        args (list): A list of postiional arguments to parse.
        kwargs (dict): A dictionary of keyword arguments to parse.
        extra (bool, default=False): Parse extra keyword arguments and
            include them in the results.
        partial (bool, default=False): Allow partial arguments to be
            parsed.

    Raises:
        BindError: If there are not enough arguments to bind to
        the function and partial=False.
    """
    args = args or []
    kwargs = kwargs or {}
    sig = inspect.signature(func)

    # Bind all args and kwargs to the main function.
    bind = sig.bind if not partial else sig.bind_partial
    try:
        bound = bind(
            *args, **{k: v for k, v in kwargs.items() if k in sig.parameters}
        )
    except TypeError as exc:
        msg = (
            f'Cannot bind arguments args={args} kwargs={kwargs}'
            f' to function "{func}" - {exc}.'
        )
        raise BindError(msg) from exc

    bound.apply_defaults()

    # We currently allow defaults, validators, and contexts
    # to take in arbitrary arguments, even if they are not part
    # of the function declaration. This is facilitated by
    # adding any additional keyword arguments to the call arguments.
    # We may later be more strict about this.
    if extra:
        for label, value in kwargs.items():
            if label not in sig.parameters:
                bound.arguments[label] = value

    return bound.arguments


class Lazy:
    """A base class for lazy utilties

    Tracks a call chain that can later be lazily evaulated.

    For example, @arg.val is a lazy utility that can
    obtain the value of an argument (@arg.val('arg_name'))
    and then apply chained operations (@arg.val('arg_name').strip() to
    strip a string for example).
    """

    def __init__(self):
        self._call_chain = []

    def __getattribute__(self, name):
        if name.startswith('_'):
            return object.__getattribute__(self, name)
        else:
            self._call_chain.append((name, None, None))
            return self

    def __call__(self, *args, **kwargs):
        if self._call_chain:
            self._call_chain[-1] = (self._call_chain[-1][0], args, kwargs)
        else:
            # If the lazy object is called before any attributes are
            # accessed, the return of the lazy object will be called
            # directly
            self._call_chain.append((None, args, kwargs))
        return self

    def _call(self, **call_args):
        raise NotImplementedError

    def _load(self, **call_args):
        """Load the lazy object and return the chained result."""
        val = self._call(**call_args)

        for name, args, kwargs in self._call_chain:
            if name is None:
                # If the name is none, the call was applied directly
                # on the return value
                val = val()
            else:
                val = getattr(val, name)
                if (args, kwargs) != (None, None):
                    # If the args/kwargs are none, an attribute
                    # was accessed. Otherwise a method was called
                    val = val(*args, **kwargs)

        return val


class func(Lazy):
    """For lazy calling of a function.

    All python-args decorator functions are wrapped in this. The
    func class lazily evaluates these functions and dynamically
    binds arguments.

    This class can still be used directly in other scenarios, although
    it is never required to use it directly in python-args decorators,
    it can be used by other python-args utilities (like arg.init).
    """

    def __init__(self, wraps, default=_unset):
        super().__init__()
        self._wraps = wraps
        self._func = wraps._func if isinstance(wraps, func) else wraps
        self._default = default

    def _call(self, **call_args):
        """Call and return function with args"""
        try:
            call_args = _parse_args(self._func, kwargs=call_args)
        except BindError:
            if self._default is not _unset:
                return self._default

            raise

        if isinstance(self._wraps, Lazy):
            return load(self._wraps, **call_args)
        else:
            return self._wraps(**call_args)


class val(func):
    """A shortcut that lazily returns the value of an argument."""

    def __init__(self, arg, default=_unset):
        self._arg = arg
        super().__init__(eval(f'lambda {arg}: {arg}'), default=default)


class first(Lazy):
    """
    Obtain the result of the first lazy method that can be executed
    without binding errors.

    Examples:

        Assign ``arg`` to a function result if the function can be bound,
        otherwise assign it to the value of ``arg2``::

            @arg.defaults(arg=arg.first(arg.func(...), arg.val('arg2')))
            def my_func(arg):
                ...

        Assign ``arg`` to the value of ``arg1``, ``arg2``, or ``arg3``.
        As shown below, passing in a string is the same for passing in
        an `arg.val`::

            @arg.defaults(arg=arg.first('arg1', 'arg2', 'arg3'))
            def my_func(arg):
                ...

        Similarly, passing in a function is the same for passing in
        an `arg.func`::

            @arg.defaults(arg=arg.first(lambda a: 'a', lambda b: 'b'))
            def my_func(arg):
                ...

        Assign ``arg`` to the value of ``arg2`` or ``arg3``. Default it to the
        value of "nothing" if none of those argument exist::

            @arg.defaults(arg=arg.first('arg1', 'arg2', default='nothing'))
            def my_func(arg):
                ...
    """

    def __init__(self, *lazy_vals, default=_unset):
        def _get_lazy_val(lazy_val):
            if isinstance(lazy_val, Lazy):
                return lazy_val
            elif isinstance(lazy_val, str):
                return val(lazy_val)
            elif callable(lazy_val):
                return func(lazy_val)
            else:
                raise TypeError(
                    f'"{lazy_val}" must be a string, function, or arg.Lazy'
                    ' object'
                )

        lazy_vals = [_get_lazy_val(lazy_val) for lazy_val in lazy_vals]
        assert all(isinstance(lazy_val, Lazy) for lazy_val in lazy_vals)
        self._lazy_vals = lazy_vals
        self._default = default
        super().__init__()

    def _call(self, **call_args):
        """Return first loadable value"""
        for lazy_val in self._lazy_vals:
            try:
                return load(lazy_val, **call_args)
            except BindError:
                pass

        if self._default is not _unset:
            return self._default
        else:
            msg = (
                f'Cannot bind arguments kwargs={call_args}'
                f' to anything in arg.first({self._lazy_vals})'
            )
            raise BindError(msg)


class init(Lazy):
    """For lazy initialization of a class.

    Args and keyword arguments can also be lazily loaded with
    arg.func, arg.init, arg.val or any lazy python-args utilities.
    """

    def __init__(self, class_, *args, **kwargs):
        super().__init__()
        self._class = class_
        self._args = args
        self._kwargs = kwargs

    def _call(self, **call_args):
        class_args = [
            load(a, **call_args) if isinstance(a, Lazy) else a
            for a in self._args
        ]
        class_kwargs = {
            l: load(v, **call_args) if isinstance(v, Lazy) else v
            for l, v in self._kwargs.items()
        }
        return self._class(*class_args, **class_kwargs)


def load(lazy, **call_args):
    """Loads a lazy object with arguments.

    We cannot override __call__ on lazy objects since lazy objects
    are chainable. So we must go through this interface to evaluate them.
    """
    # Any non-lazy objects are assumed to be lazy functions
    if not isinstance(lazy, Lazy):
        lazy = func(lazy)

    return lazy._load(**call_args)


@contextlib.contextmanager
def _suppress_bind_errors_in_partial_call():
    """
    When dynamically binding arguments to contexts, validators, defaults,
    etc, suppress errors when inside of the special partial context
    """
    try:
        yield
    except BindError:
        if not call().is_partial:
            raise


class Args:
    """
    The primary Args class that orchestrates running of ``python-args``
    decorators.

    Responsible for parsing call args and orchestrating various
    run modes. Can be used to construct other top-level ``python-args``
    decorators that interface with the library.
    """

    def __init__(self, wraps):
        # The main underlying function that is wrapped. If we are wrapping
        # another Args object (such as when stacking decorators), pull
        # the _func from the underlying Args object so that we always
        # have a reference to it.
        self._func = wraps if not isinstance(wraps, Args) else wraps._func
        self._wraps = wraps

    @property
    def func(self):
        return self._func

    @property
    def partial(self):
        """
        Return a partial version of the Args where validators, contexts,
        and defaults can run against partial arguments.
        """
        return contexts(func(call).set(is_partial=True))(self)

    @property
    def pre_func(self):
        """
        Return a version of the Args where everything before the main
        function runs.
        """
        return contexts(func(call).set(is_pre_func=True))(self)

    def _call(self, call_args):
        """
        Call the wrapped function and returns the result.

        Ignore calling if we are only running pre_func routines.
        """
        if isinstance(self._wraps, Args):
            return self._wraps._call(call_args)
        elif not call().is_pre_func:
            # We have reached the end of the Args chain. Ignore
            # running the function if we are in pre_func mode. Otherwise
            # parse the final arguments against the function and call.
            # We re-parse the arguments so that we can throw a nicer
            # BindError if anything is going on with our arguments
            assert self._wraps == self._func
            call_args = _parse_args(self.func, kwargs=call_args)
            return self._func(**call_args)

    def __call__(self, *args, **kwargs):
        """
        The entry point for the python-args call chain. Any nested
        decorators will start here.
        """
        if hasattr(_current_call, 'val'):
            raise AssertionError('Can only call Args class once in chain.')

        _current_call.val = Call()
        try:
            call_args = _parse_args(
                self.func, args, kwargs, partial=True, extra=True
            )
            return self._call(call_args)
        finally:
            delattr(_current_call, 'val')


class Validators(Args):
    def __init__(self, wraps, validators):
        self._validators = validators
        super().__init__(wraps)

    def _call(self, kwargs):
        for validator_func in self._validators:
            with _suppress_bind_errors_in_partial_call():
                load(validator_func, **kwargs)

        return super()._call(kwargs)


def validators(*validation_funcs):
    """
    Run validators over arguments.

    Args:
        *validation_funcs (List[func]): Functions that validate arguments.
            Argument names of the calling function are used to determine
            which validators to run.

    Examples:
        Validate an email address is correct:::

            def validate_email(email):
                if email.not_valid_address():
                    raise ValueError('Email is invalid')

            @arg.validators(validate_email)
            def my_func(email):
                # A ValueError will be raised when calling with an invalid email
    """

    def decorator(wraps):
        return Validators(wraps, validators=validation_funcs)

    return decorator


class Contexts(Args):
    def __init__(self, wraps, contexts):
        self._contexts = contexts
        super().__init__(wraps)

    def _call(self, call_args):
        context_args = {}

        with contextlib.ExitStack() as context_stack:
            for context_key, context_func in self._contexts.items():
                with _suppress_bind_errors_in_partial_call():
                    resource = context_stack.enter_context(
                        load(context_func, **{**call_args, **context_args})
                    )

                    # The call arguments to the current call are expanded when
                    # entering named contexts. Named
                    # context managers are those that assign a resource to
                    # a name (i.e. @arg.contexts(name=context_manager)).
                    # If not named, the context key is just the reference
                    # to the context function.
                    if isinstance(context_key, str):
                        context_args[context_key] = resource

            return super()._call({**call_args, **context_args})


def contexts(*context_managers, **named_context_managers):
    """
    Enter contexts based on arguments.

    Args:
        *context_managers (List[contextmanager]): A list of context managers
            that will be entered before calling the function. Context managers
            can take arguments that the function takes.
        **named_context_managers (Dict[contextmanagers]): Naming a context
            manager will assign the context manager resource to the argument
            name, allowing the function (or other args decorators) to use
            it.
    """

    def decorator(wraps):
        return Contexts(
            wraps,
            contexts={
                **{mgr: mgr for mgr in context_managers},
                **named_context_managers,
            },
        )

    return decorator


class Defaults(Args):
    def __init__(self, wraps, defaults):
        self._defaults = defaults
        super().__init__(wraps)

    def _call(self, call_args):
        default_args = {}
        # Apply processing for defaults
        for label, default_func in self._defaults.items():
            with _suppress_bind_errors_in_partial_call():
                default_args[label] = load(
                    default_func, **{**call_args, **default_args}
                )

        return super()._call({**call_args, **default_args})


def defaults(**default_funcs):
    """
    Process default values to function arguments.

    Args:
        **default_funcs (Dict[func]): A mapping of argument names to
            functions that should process those arguments before
            they are provided to the function call.

    Examples:
        Pre-process a string argument so that it is always uppercase::

            @arg.defaults(arg_name=lambda arg_name: arg_name.upper())
            def my_func(arg_name):
                # arg_name will be the uppercase version when my_func is called
    """

    def decorator(wraps):
        return Defaults(wraps, defaults=default_funcs)

    return decorator


class Parametrize(Args):
    def __init__(self, wraps, parametrize):
        # We currently only support parametrizing exactly one argument
        assert len(parametrize) == 1
        self._parametrize_arg = list(parametrize)[0]
        self._parametrize_func = parametrize[self._parametrize_arg]
        super().__init__(wraps)

    def _call(self, call_args):
        with _suppress_bind_errors_in_partial_call():
            arg_vals = load(self._parametrize_func, **call_args)
            results = []
            for arg_index, arg_val in enumerate(arg_vals):
                with call().set(
                    parametrize_arg=self._parametrize_arg,
                    parametrize_arg_val=arg_val,
                    parametrize_arg_vals=arg_vals,
                    parametrize_arg_index=arg_index,
                ):
                    results.append(
                        super()._call(
                            {**call_args, **{self._parametrize_arg: arg_val}}
                        )
                    )

            return results

        # If we are in partial mode and couldn't bind, keep trying to
        # run partially
        return super()._call(call_args)


def parametrize(**parametrize_funcs):
    """
    Parametrize a function's arguments.

    Args:
        **parametrize_funcs (Dict[func]): A mapping of argument names to
            functions that return iterables. The argument will
            be parametrized over the iterable, calling the underlying
            function for each element.

    Returns:
        list: Parametrized functions return a list of all results.

    Examples:
        This is an example of parametrizing a function that doubles a value::

            @arg.parametrize(val=arg.val('vals'))
            def double(val):
                return val * 2

            assert double(vals=[1, 2, 3]) == [2, 4, 6]
    """

    def decorator(wraps):
        return Parametrize(wraps, parametrize=parametrize_funcs)

    return decorator


def s(*arg_decorators):
    """
    Creates a ``python-args`` class from multiple decorators. Useful
    for creating higher-level methods of running functions.

    Args:
        *arg_decorators (List[`Args`]): A list of ``python-args``
            decorators (``@arg.validators``, ``@arg.contexts``, etc)

    Returns:
        `Args`: An `Args` class with the appropriate decorators applied.
        If no ``arg_decorators`` are provided, will return an `Args`
        class with no decorators.
    """

    def decorator(wraps):
        for arg_decorator in reversed(arg_decorators):
            wraps = arg_decorator(wraps)

        if not isinstance(wraps, Args):
            wraps = Args(wraps)

        return wraps

    return decorator
