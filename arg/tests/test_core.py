import contextlib
import logging

import pytest

import arg


def test_call_outside_args():
    """Tests arg.call() when no python-args func is running"""
    assert arg.call() is None


def test_basic_defaults_decorator(caplog):
    """Tests basic usage of arg.defaults decorator"""

    @arg.defaults(arg=lambda arg: arg.upper())
    def my_func_with_defaults(arg, kwarg=None):
        return arg, kwarg

    assert my_func_with_defaults('to_upper') == ('TO_UPPER', None)


def test_dependent_defaults_decorator(caplog):
    """Tests usage of arg.defaults decorator when depending on other args"""

    @arg.defaults(arg1=lambda arg2: arg2.upper(), arg3=lambda extra: extra)
    def my_func_with_defaults(arg1, arg2, arg3):
        return arg1, arg2, arg3

    assert my_func_with_defaults(arg2='arg2', extra='extra') == (
        'ARG2',
        'arg2',
        'extra',
    )


def test_func():
    """Tests usage of the arg.func utility for lazily-evaluating functions"""
    lazy_func = arg.func(lambda: '1')
    assert arg.load(lazy_func) == '1'

    def upper_arg(arg):
        return arg.upper()

    lazy_func = arg.func(upper_arg)
    assert arg.load(lazy_func, arg='hi') == 'HI'

    # Trying to run a lazy func without proper args results in a bind error
    with pytest.raises(arg.BindError):
        assert arg.load(lazy_func) == 'default'

    # Provide a default when arguments cannot be bound
    lazy_func = arg.func(upper_arg, 'default')
    assert arg.load(lazy_func) == 'default'


def test_init():
    """Tests usage of the arg.init utility for lazily initializing classes"""

    class LazyClass:
        def __init__(self, arg, kwarg=None):
            self.arg = arg
            self.kwarg = kwarg

    lazy_class = arg.init(LazyClass, 'arg', kwarg='kwarg')
    inst = arg.load(lazy_class)
    assert inst.arg == 'arg'
    assert inst.kwarg == 'kwarg'

    # Verify we can use other lazy objects as parameters to class
    # initialization
    lazy_class = arg.init(
        LazyClass, 'arg', kwarg=arg.func(lambda extra: extra)
    )
    inst = arg.load(lazy_class, extra='extra')
    assert inst.arg == 'arg'
    assert inst.kwarg == 'extra'


def test_val():
    """Tests the arg.val utility function for lazily obtaining values"""
    assert arg.load(arg.val('arg_name'), arg_name=1) == 1
    with pytest.raises(arg.BindError):
        assert arg.load(arg.val('arg_name'), missing_arg=2)
    assert arg.load(arg.val('arg_name', 1), missing_arg=2) == 1


def test_first():
    """Tests arg.first utility for lazily loading the first loadable value"""
    assert arg.load(arg.first(arg.val('a'), arg.val('b')), b=2) == 2
    assert arg.load(arg.first(arg.val('a'), arg.val('b')), a=3) == 3
    with pytest.raises(arg.BindError):
        arg.load(arg.first(arg.val('a'), arg.val('b')), c=3)

    with pytest.raises(TypeError):
        arg.first(1, 2, 3)

    assert arg.load(arg.first(lambda a: '1', lambda b: '2'), b='val') == '2'

    assert (
        arg.load(arg.first(arg.val('a'), arg.val('b'), default='nothing'), c=3)
        == 'nothing'
    )

    assert arg.load(arg.first('a', 'b', 'c', 'd'), c=2, d=3) == 2


def test_lazy_evaluation_chaining():
    """Verifies that we can chain calls to lazy objects"""
    assert arg.load(arg.val('value').upper(), value='aa') == 'AA'
    assert arg.load(arg.val('value').upper().lower(), value='Aa') == 'aa'
    assert arg.load(arg.val('func_val')(), func_val=lambda: 'ret') == 'ret'

    class MyClass:
        def __init__(self, val):
            self.val = val

    # Instantiate a class with a dynamic attribute and return an attribute
    # of that class
    assert arg.load(arg.init(MyClass, val=arg.val('a')).val, a='hi') == 'hi'


def test_nested_lazy_calling():
    """Verifies that lazy objects can be nested in others"""
    assert (
        arg.load(arg.func(arg.func(lambda value: value).upper()), value='hi')
        == 'HI'
    )


def test_basic_contexts_decorator(caplog):
    """Tests arg.contexts decorator with contexts that take no arguments"""
    caplog.set_level(logging.INFO)

    @contextlib.contextmanager
    def logging_context():
        """A context manager that logs"""
        logging.info('starting')
        yield
        logging.info('stopping')

    @arg.contexts(logging_context)
    def my_wrapped_function(arg, kwarg=None):
        return arg, kwarg

    assert my_wrapped_function('arg', kwarg='kwarg') == ('arg', 'kwarg')
    assert caplog.record_tuples == [
        ('root', logging.INFO, 'starting'),
        ('root', logging.INFO, 'stopping'),
    ]


@pytest.mark.parametrize(
    'kwargs, expected_logs',
    [
        (
            {},
            [
                ('root', logging.INFO, 'starting None'),
                ('root', logging.INFO, 'stopping None'),
            ],
        ),
        (
            {'value_to_log': 'value'},
            [
                ('root', logging.INFO, 'starting value'),
                ('root', logging.INFO, 'stopping value'),
            ],
        ),
    ],
)
def test_contexts_with_arguments_decorator(caplog, kwargs, expected_logs):
    """Tests arg.contexts decorator with contexts that take arguments"""
    caplog.set_level(logging.INFO)

    @contextlib.contextmanager
    def logging_context(value_to_log):
        """A context manager that logs"""
        logging.info(f'starting {value_to_log}')
        yield
        logging.info(f'stopping {value_to_log}')

    @arg.contexts(logging_context)
    def my_wrapped_function(arg, value_to_log=None):
        return arg, value_to_log

    my_wrapped_function('arg', **kwargs)
    assert caplog.record_tuples == expected_logs


def test_named_contexts_decorator():
    """Verifies that named contexts are used as function arguments"""

    @contextlib.contextmanager
    def named_context():
        yield 'value'

    @arg.contexts(arg=named_context)
    def my_wrapped_function(arg):
        return arg

    assert my_wrapped_function() == 'value'


def test_contexts_that_suppress_errors():
    """Verifies that contexts can suppress errors"""

    @contextlib.contextmanager
    def suppress_exceptions():
        try:
            yield
        except Exception:
            pass

    @arg.contexts(suppress_exceptions)
    def hello():
        raise ValueError

    with suppress_exceptions():
        hello.func()

    assert hello() is None


def test_basic_validators_decorator():
    """Tests arg.validators decorator with validators that take no arguments"""

    def passes_validation():
        """A validator that always passes"""
        pass

    def fails_validation():
        """A validator that always fails"""
        raise Exception

    @arg.validators(passes_validation)
    def my_passing_function(arg, kwarg=None):
        return arg, kwarg

    @arg.validators(passes_validation, fails_validation)
    def my_failing_function(arg, kwarg=None):
        pass

    assert my_passing_function('arg', kwarg='kwarg') == ('arg', 'kwarg')
    with pytest.raises(Exception):
        my_failing_function('arg', kwarg='kwarg')


@pytest.mark.parametrize(
    'kwargs, expected_logs',
    [
        (
            {},
            [
                ('root', logging.INFO, 'passing arg1_value'),
                ('root', logging.INFO, 'failing None'),
            ],
        ),
        (
            {'arg2': 'value'},
            [
                ('root', logging.INFO, 'passing arg1_value'),
                ('root', logging.INFO, 'failing value'),
            ],
        ),
    ],
)
def test_validators_with_arguments_decorator(caplog, kwargs, expected_logs):
    """Tests arg.validators decorator with validators that take arguments"""
    caplog.set_level(logging.INFO)

    def passes_validation(arg1):
        """A validator that always passes"""
        logging.info(f'passing {arg1}')

    def fails_validation(arg2):
        """A validator that always fails"""
        logging.info(f'failing {arg2}')
        raise Exception

    @arg.validators(passes_validation, fails_validation)
    def my_failing_function(arg1, arg2=None):
        pass

    with pytest.raises(Exception):
        my_failing_function('arg1_value', **kwargs)

    assert caplog.record_tuples == expected_logs


def test_basic_validators_interface():
    """
    Tests the interfaces created from decorating a function with arg.validators
    """

    def fails():
        """A validator that always fails"""
        raise RuntimeError

    @arg.validators(fails)
    def my_failing_function(arg, kwarg=None):
        return arg, kwarg

    with pytest.raises(RuntimeError):
        my_failing_function('arg', kwarg='kwarg')

    with pytest.raises(RuntimeError):
        my_failing_function.pre_func('arg', kwarg='kwarg')

    assert my_failing_function.func('arg', kwarg='kwarg') == ('arg', 'kwarg')


def test_nested_validators_interface():
    """
    Verifies that validation can be called on all validators no matter
    how nested the Args are.
    """

    def passes():
        """A validator that always passes"""
        return True

    def fails():
        """A validator that always fails"""
        raise RuntimeError

    @arg.validators(passes)
    @arg.validators(fails)
    def fails_validators(arg, kwarg=None):
        return arg, kwarg

    with pytest.raises(RuntimeError):
        fails_validators.pre_func('arg', kwarg='kwarg')

    assert fails_validators.func('arg', kwarg='kwarg') == ('arg', 'kwarg')

    # Test a failing function where all validators pass
    @arg.validators(passes)
    @arg.validators(passes)
    def fails_function(arg, kwarg=None):
        raise ValueError

    fails_function.pre_func('arg', kwarg='kwarg')

    with pytest.raises(ValueError):
        fails_function('arg', kwarg='kwarg')

    with pytest.raises(ValueError):
        fails_function.func('arg', kwarg='kwarg')


def test_nested_partial_validators_interface():
    """
    Verifies that validation can be partially executed depending on
    the arguments.
    """

    def passes(arg1):
        """A validator that always passes"""
        return True

    def fails(arg2):
        """A validator that always fails"""
        raise RuntimeError

    @arg.validators(passes)
    @arg.validators(fails)
    def fails_validators(arg1, arg2):
        return arg1, arg2

    with pytest.raises(RuntimeError):
        fails_validators.pre_func('arg1', 'arg2')

    # Run in partial mode, only running the validator for arg2 (which fails)
    with pytest.raises(RuntimeError):
        fails_validators.partial.pre_func(arg2='arg2')

    # Run in partial mode, only running the validator for arg1 (which succeeds)
    fails_validators.partial.pre_func(arg1='arg1')

    # Running outside of partial mode and only giving partial args fails
    with pytest.raises(arg.BindError):
        fails_validators.pre_func(arg1='arg1')


def test_validators_with_defaults():
    """
    Tests processing defaults before validators
    """

    def check_that_upper_is_invalid(arg1):
        if arg1 == 'UPPER':
            raise ValueError

    @arg.defaults(arg1=arg.val('arg1').upper())
    @arg.validators(check_that_upper_is_invalid)
    def my_func(arg1):
        return arg1

    with pytest.raises(ValueError):
        my_func(arg1='upper')

    assert my_func(arg1='lower') == 'LOWER'


def test_s_arg_wrapper():
    """Tests the arg.s wrapper utility

    Simulates the same test scenario as test_validators_with_defaults()
    """

    def fails(arg1):
        """A validator that always passes"""
        if arg1 == 'UPPER':
            raise ValueError

    def my_func(arg1):
        return arg1

    my_func_runner = arg.s(
        arg.defaults(arg1=arg.val('arg1').upper()), arg.validators(fails)
    )

    with pytest.raises(ValueError):
        my_func_runner(my_func)(arg1='upper')

    assert my_func_runner(my_func)(arg1='lower') == 'LOWER'

    assert isinstance(arg.s()(my_func), arg.Args)
    assert arg.s()(my_func)('hello') == 'hello'


def test_parametrize():
    """Tests parametrizing a function"""

    @arg.parametrize(val=arg.val('vals'))
    def double(val):
        return val * 2

    assert double(vals=[1, 2, 3]) == [2, 4, 6]

    # This should result in a lazy bind error
    with pytest.raises(arg.BindError):
        double(val=1)

    # Partial runs should be able to ignore parametrization
    assert double.partial(val=1) == 2


def test_parametrize_call_context():
    """Tests that the proper call context is set during parameterization"""

    arg_names = []
    arg_vals = []
    arg_indexes = []

    @contextlib.contextmanager
    def gather_parametrized_context():
        arg_names.append(arg.call().parametrize_arg)
        arg_vals.append(arg.call().parametrize_arg_val)
        arg_indexes.append(arg.call().parametrize_arg_index)
        yield

    @arg.parametrize(val=arg.val('vals'))
    @arg.contexts(gather_parametrized_context)
    def double(val):
        return val * 2

    assert double(vals=[1, 2, 3]) == [2, 4, 6]

    # Verify that context was properly set during the run
    assert arg_names == ['val', 'val', 'val']
    assert arg_vals == [1, 2, 3]
    assert arg_indexes == [0, 1, 2]


def test_unsuppored_parametrize_args():
    """Tests parametrizing a function with unsuppored arguments"""

    with pytest.raises(AssertionError):

        @arg.parametrize(val=arg.val('vals'), val2=arg.val('vals'))
        def nothing(val):
            pass
