python-args
############

python-args, inspired by `attrs <https://www.attrs.org/en/stable/>`__,
removes the boilerplate of processing arguments to functions and methods.

Decorating your functions with python-args decorators like ``arg.validators``
can make your code more composable, more readable, and easier to test. Along
with this, functions decorated with python-args can be used to by other tools
and frameworks to build more expressive interfaces. The
`django-args <https://github.com/jyveapp/django-args>`__ and
`django-action-framework <https://github.com/jyveapp/django-action-framework>`__
libraries are two examples.

The core ``python-args`` decorators are as follows:

1. ``@arg.validators(*validation_funcs)``: Runs validation functions that
   can take the same named arguments as the decorated function. When
   decorating a function with `arg.validators`, you not only de-couple
   your function from argument validation logic, but ``python-args``
   will allow other interfaces to only run the validators of your function.
2. ``@arg.defaults(**arg_default_funcs)``: Sets arguments to default
   values. The default functions can similarly take the same named
   parameters of the decorated function.
3. ``@arg.parametrize(**parametrize_funcs)``: Runs a function multiple times
   for a particular input.
4. ``@arg.contexts(*context_funcs)``: Enters context managers before
   a function. Context managers can take the same named parameters as the
   decorated function.

`View the docs here <https://python-args.readthedocs.io/>`__
for a tutorial and more examples of how ``python-args`` can be used in
practice.

Documentation
=============

`View the python-args docs here <https://python-args.readthedocs.io/>`_.

Installation
============

Install python-args with::

    pip3 install python-args


Contributing Guide
==================

For information on setting up python-args for development and
contributing changes, view `CONTRIBUTING.rst <CONTRIBUTING.rst>`_.

Primary Authors
===============

- @wesleykendall (Wes Kendall)
