import bleach
import re

cdef list[str] ALLOWED_TAGS = [
    "p", "br", "b", "i", "strong", "em", "u", "ul", "ol", "li",
    "blockquote", "code", "pre", "a", "img", "div", "span",
    "table", "tr", "td", "th", "thead", "tbody"
]

cdef tuple[bint, object] false_return = (False, None)
cdef tuple[bint, object] true_return = (True, None)


cdef str str_filter(str value, str filter):
    if filter == "xss":
        return bleach.clean(value, tags=ALLOWED_TAGS)


cdef inline bint _value_max_len(list value, int limit):
    cdef Py_ssize_t i, n = len(value)
    for i in range(n):
        if len(str(value[i])) > limit:
            return False
    return True


cdef inline bint _value_min_len(list value, int limit):
    cdef Py_ssize_t i, n = len(value)
    for i in range(n):
        if len(str(value[i])) < limit:
            return False
    return True


cdef class Validator:
    cdef dict[str, object] options

    def __init__(self, dict options) -> None:
        self.options = options

    cpdef tuple[bint, object] validate_dict(self, dict value):
        return true_return

    cpdef tuple[bint, object] validate_bool(self, object value):
        if isinstance(value, bool):
            return True, value
        return false_return

    cpdef tuple[bint, object] validate_list(self, list[object] value):
        cdef dict options = self.options

        cdef list[str] checks = [
            "min_len",
            "max_len",
            "len",
            "value_max_len",
            "value_min_len"
        ]
        cdef object option_value

        for option in checks:
            if option not in options:
                continue

            option_value = options[option]

            if option == "min_len" and not len(value) >= int(option_value):
                return false_return
            elif option == "max_len" and not len(value) <= int(option_value):
                return false_return
            elif option == "len" and not len(value) == int(option_value):
                return false_return
            if option == "value_max_len" and not _value_max_len(value, int(option_value)):
                return false_return
            elif option == "value_min_len" and not _value_min_len(value, int(option_value)):
                return false_return

        return true_return

    cpdef tuple[bint, object] validate_int(self, int value):
        cdef dict options = self.options

        cdef list[str] checks = [
            "min",
            "max"
        ]
        cdef object option_value

        for option in checks:
            if option not in options:
                continue

            option_value = options[option]

            if option == "min" and not value >= int(option_value):
                return false_return
            elif option == "max" and not value <= int(option_value):
                return false_return

        return true_return

    cpdef tuple[bint, object] validate_str(self, str value):
        cdef dict options = self.options
        cdef list[str] checks = [
            "min_len",
            "max_len",
            "len",
            "values"
        ]

        if "regex" in options:
            if not re.match(options["regex"], value):
                return false_return

        cdef object option_value

        for option in checks:
            if option not in options:
                continue

            option_value = options[option]
            
            if option == "min_len" and not len(value) >= int(option_value):
                return false_return
            elif option == "max_len" and not len(value) <= int(option_value):
                return false_return
            elif option == "len" and not len(value) == int(option_value):
                return false_return
            elif option == "values" and not value in option_value:
                return false_return

        if "filter" in options:
            if isinstance(options["filter"], list):
                for filter in options["filter"]:
                    value = str_filter(value, filter)
            if isinstance(options["filter"], str):
                value = str_filter(value, options["filter"])

        return True, value

    cpdef tuple[bint, object] validate_email(self, str value):
        cdef dict options = self.options
        options["min_len"] = 4
        options["max_len"] = 254
        options["regex"] = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return self.validate_str(value)

    cpdef tuple[bint, object] parameters_str(self, str value):
        return self.validate_str(value)

    cpdef tuple[bint, object] parameters_int(self, str value):
        if not value.isdigit():
            return false_return

        _value = int(value)
        return self.validate_int(_value)[0], _value

    cpdef tuple[bint, object] parameters_bool(self, str value):
        cdef str _value = value.lower()
        return _value in ["true", "false"], _value == "true"

    cpdef tuple[bint, object] parameters_list(self, str value):
        cdef dict options = self.options

        if "f_max_len" in options and len(value) > int(options["f_max_len"]):
            return false_return

        cdef list[str] _value = value.split(",")

        cdef list[str] checks = [
            "min_len",
            "max_len",
            "len"
        ]

        cdef object option_value

        for option in checks:
            if option not in options:
                continue

            option_value = options[option]
            
            if option == "min_len" and not len(_value) >= int(option_value):
                return false_return
            elif option == "max_len" and not len(_value) <= int(option_value):
                return false_return
            elif option == "len" and not len(_value) == int(option_value):
                return false_return

        cdef list[str] v_checks = [
            "v_min_len",
            "v_max_len",
            "v_len",
            "is_digit"
        ]

        for option in v_checks:
            if option not in options:
                continue

            option_value = options[option]

            for x in _value:
                if option == "v_min_len" and not len(x) >= int(option_value):
                    return false_return
                elif option == "v_max_len" and not len(x) <= int(option_value):
                    return false_return
                elif option == "v_len" and not len(x) == int(option_value):
                    return false_return
                elif option == "is_digit" and not str(x).isdigit():
                    return false_return

        return True, _value
