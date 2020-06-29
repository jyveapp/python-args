# Changelog
## 1.0.2 (2020-06-29)
### Trivial
  - Return None on arg.call when outside of python-args instead of an AssertionError [Wes Kendall, 294fb29]

## 1.0.1 (2020-06-29)
### Trivial
  - Added additional docs to the README [Wes Kendall, e6d2f12]

## 1.0.0 (2020-06-24)
### Api-Break
  - The initial release of python-args [Wes Kendall, 8705bbd]

    V1 of `python-args` helps take the boilerplate out of processing arguments
    to python functions. Similar to `attrs`, `python-args` provides decorators
    to do the following:

    1. `@arg.validators(...)`: Run validation functions over the arguments to
       your function. When using `@arg.validators`, your function also has
       an additional interface to run only the validators or the wrapped
       function.
    2. `@arg.contexts(...)`: Wrap your function in context managers. Similar
       to validators, context managers can also take in the arguments to
       the function as arguments to the context manager.
    3. `@arg.defaults(...)`: Process default values for your arguments from
       callables. Default values are processed before validation, making
       validations run seamlessly with the additional processing that goes
       on for default values to function calls.
    4. `@arg.parametrize(...)`: Parametrize an argument over multiple calls
       to the wrapped function.

    Each function of `python-args` is lazily evaluated when the primary
    function is called. Although this happens under the scenes, users
    can take advantage of `python-args` `Lazy` objects to avoid
    having `lambda` functions everywhere. V1 comes with the following
    lazy utilities:

    1. `arg.func(func, default)`: Call a function that may take arguments
       to the calling function. If the arguments cannot be bound to
       the calling arguments, return the default.
    2. `arg.val(arg_name)`: Return the value of the argument. This is
       a utility method that wraps `arg.func` to lazily return the
       called argument value. This helps alleviate boilerplate with
       preprocessing argument values.
    3. `arg.init(*args, **kwargs)`: Lazily initialize a class.
    4. `arg.first(*args, default)`: Obtain the first bound argument with
       a given name.

    All lazy utilities can be chained. For example, `arg.val('name').upper()`
    will return the uppercase version of the argument named "name".

    Lazy utilities don't have to only be used with `python-args` decorators.
    They can manually be called with `args.call(lazy_obj, **lazy_args)`, and
    users can construct other lazy utilities by inherting the `arg.Lazy`
    object.

