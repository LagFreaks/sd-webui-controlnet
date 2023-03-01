import re

from modules import scripts, shared

try:
    from scripts import controlnet
except ImportError:
    import_error = True
else:
    import_error = False

DEBUG_MODE = False


def debug_info(func):
    def debug_info_(*args, **kwargs):
        if DEBUG_MODE:
            print(f"Debug info: {func.__name__}, {args}")
        return func(*args, **kwargs)
    return debug_info_


def find_dict(dict_list, keyword, search_key="name", stop=False):
    result = next((d for d in dict_list if d[search_key] == keyword), None)
    if result or not stop:
        return result
    else:
        raise ValueError(f"Dictionary with value '{keyword}' in key '{search_key}' not found.")


def flatten_list(lst):
    result = []
    for element in lst:
        if isinstance(element, list):
            result.extend(flatten_list(element))
        else:
            result.append(element)
    return result


def is_all_included(target_list, check_list, allow_blank=False, stop=False):
    for element in flatten_list(target_list):
        if allow_blank and str(element) in ["None", ""]:
            continue
        elif element not in check_list:
            if not stop:
                return False
            else:
                raise ValueError(f"'{element}' is not included in check list.")
    return True


################################################################
################################################################
#
# Starting the main process of this module.
#
################################################################
################################################################


def find_module(module_names):
    if isinstance(module_names, str):
        module_names = [s.strip() for s in module_names.split(",")]
    for data in scripts.scripts_data:
        if data.script_class.__module__ in module_names and hasattr(data, "module"):
            return data.module
    return None


def add_axis_options(xyz_grid):
    # This class is currently meaningless.
    class AxisOption(xyz_grid.AxisOption):
        """This class returns an instance of the xyz_grid.AxisOption class.

        If clone is not specified, a single instance is returned.
        If clone is True, the number of copies is
        obtained from control_net_max_models_num and a list is returned.
        If clone is an integer greater than 1,
        that number of copies is made and returned as a list.
        """
        def __new__(cls, *args, clone=None, **kwargs):
            def init(this):
                cls.__init__(this, *args, **kwargs)
            if clone:
                this = super().__new__(cls)
                init(this)
                return this._clone(clone)
            else:
                this = super().__new__(xyz_grid.AxisOption)
                init(this)
                return this

        def _clone(self, num=True):
            def copy(self):
                return self.__class__(**self.__dict__)
            if num is True:
                num = shared.opts.data.get("control_net_max_models_num", 1)
            instance_list = [copy(self)]
            for i in range(1, num):
                instance = copy(self)
                instance.label = f"{self.label} - {i}"
                apply_func = self.apply.__kwdefaults__["enclosure"]
                apply_arg = f"{self.apply.__kwdefaults__['field']}_{i}"
                instance.apply = apply_func(apply_arg)
                instance_list.append(instance)
            return instance_list

    def normalize_list(valslist, type_func=None, allow_blank=True, excluded=None):
        """This function restores a broken list caused by the following process
        in the xyz_grid module.
            -> valslist = [x.strip() for x in chain.from_iterable(
                                                csv.reader(StringIO(vals)))]
        It also performs type conversion,
        adjusts the number of elements in the list, and other operations.
        """
        def search_bracket(string, bracket="[", replace=None, excluded=None):
            if excluded:
                excluded = "|".join(excluded)

            if bracket == "[":
                pattern = rf"^\[(?!(?:{excluded})\])" if excluded else r"^\["
            elif bracket == "]":
                pattern = rf"(?<!\[(?:{excluded}))\]$" if excluded else r"\]$"
            else:
                raise ValueError(f"Invalid argument provided. (bracket: {bracket})")

            if replace is None:
                return re.search(pattern, string)
            else:
                return re.sub(pattern, replace, string)

        def sublist_exists(valslist, excluded=None):
            return any(search_bracket(s, excluded=excluded) for s in valslist)

        def type_convert(valslist, type_func, allow_blank=True):
            for i, s in enumerate(valslist):
                if isinstance(s, list):
                    type_convert(s, type_func, allow_blank)
                elif allow_blank and (str(s) in ["None", ""]):
                    valslist[i] = None
                elif type_func:
                    valslist[i] = type_func(s)
                else:
                    valslist[i] = s

        def fix_list_structure(valslist, excluded=None):
            def is_same_length(list1, list2):
                return len(list1) == len(list2)

            start_indices = []
            end_indices = []
            for i, s in enumerate(valslist):
                if is_same_length(start_indices, end_indices):
                    if s != (s := search_bracket(s, "[", replace="", excluded=excluded)):
                        start_indices.append(i)
                if not is_same_length(start_indices, end_indices):
                    if s != (s := search_bracket(s, "]", replace="", excluded=excluded)):
                        end_indices.append(i + 1)
                valslist[i] = s
            if not is_same_length(start_indices, end_indices):
                raise ValueError(f"Lengths of {start_indices} and {end_indices} are different.")
            # Restore the structure of a list.
            for i, j in zip(reversed(start_indices), reversed(end_indices)):
                valslist[i:j] = [valslist[i:j]]

        def pad_to_longest(valslist):
            max_length = max(len(sub_list) for sub_list in valslist if isinstance(sub_list, list))
            for i, sub_list in enumerate(valslist):
                if isinstance(sub_list, list):
                    valslist[i] = sub_list + [None] * (max_length-len(sub_list))

        ################################################
        # Starting the main process of the normalize_list function.
        #
        if not sublist_exists(valslist, excluded):
            type_convert(valslist, type_func, allow_blank)
            return
        else:
            fix_list_structure(valslist, excluded)
            type_convert(valslist, type_func, allow_blank)
            pad_to_longest(valslist)
            return

    ################################################
    ################################################
    #
    # Define a function to pass to the AxisOption class from here.
    #
    ################################################
    ################################################

    def enable_script_control():
        shared.opts.data["control_net_allow_script_control"] = True

    def apply_field(field):
        @debug_info
        def apply_field_(p, x, xs, *, field=field, enclosure=apply_field):
            enable_script_control()
            setattr(p, field, x)

        return apply_field_

    ################################################
    # Set this function as the type attribute of the AxisOption class.
    # To skip the following processing of xyz_grid module.
    #   -> valslist = [opt.type(x) for x in valslist]
    # Perform type conversion using the function
    # set to the confirm attribute instead.
    #
    def identity(x):
        return x

    ################################################
    # The confirm function defined in this module
    # enables list notation and performs type conversion.
    #
    # Example:
    #     any = [any, any, any, ...]
    #     [any] = [any, None, None, ...]
    #     [None, None, any] = [None, None, any]
    #     [,,any] = [None, None, any]
    #     any, [,any,] = [any, any, any, ...], [None, any, None]
    #
    #     Enabled Only:
    #         any = [any] = [any, None, None, ...]
    #         (any and [any] are considered equivalent)
    #
    def confirm(func_or_str):
        @debug_info
        def confirm_(p, xs):
            if callable(func_or_str):           # func_or_str is type_func
                normalize_list(xs, func_or_str, allow_blank=True)
                return

            elif isinstance(func_or_str, str):  # func_or_str is keyword
                valid_data = find_dict(validation_data, func_or_str, stop=True)
                type_func = valid_data["type"]
                exclude_list = valid_data["exclude"]() if valid_data["exclude"] else None
                check_list = valid_data["check"]()

                normalize_list(xs, type_func, allow_blank=True, excluded=exclude_list)
                is_all_included(xs, check_list, allow_blank=True, stop=True)
                return

            else:
                raise TypeError(f"Argument must be callable or str, not {type(func_or_str).__name__}.")

        return confirm_

    def bool_(string):
        string = str(string)
        if string in ["None", ""]:
            return None
        elif string.lower() in ["true", "1"]:
            return True
        elif string.lower() in ["false", "0"]:
            return False
        else:
            raise ValueError(f"Could not convert string to boolean: {string}")

    def choices_bool():
        return ["False", "True"]

    def choices_model():
        controlnet.update_cn_models()
        return list(controlnet.cn_models_names.values())

    def choices_resize_mode():
        return ["Envelope (Outer Fit)", "Scale to Fit (Inner Fit)", "Just Resize"]

    def choices_preprocessor():
        return list(controlnet.Script().preprocessor)

    def make_excluded_list():
        pattern = re.compile(r"\[(\w+)\]")
        return [match.group(1) for s in choices_model()
                for match in pattern.finditer(s)]

    validation_data = [
        {"name": "model", "type": str, "check": choices_model, "exclude": make_excluded_list},
        {"name": "resize_mode", "type": str, "check": choices_resize_mode, "exclude": None},
        {"name": "preprocessor", "type": str, "check": choices_preprocessor, "exclude": None},
    ]

    extra_axis_options = [
        AxisOption("[ControlNet] Enabled", identity, apply_field("control_net_enabled"), confirm=confirm(bool_), choices=choices_bool),
        AxisOption("[ControlNet] Model", identity, apply_field("control_net_model"), confirm=confirm("model"), choices=choices_model, cost=0.9),
        AxisOption("[ControlNet] Weight", identity, apply_field("control_net_weight"), confirm=confirm(float)),
        AxisOption("[ControlNet] Guidance Start", identity, apply_field("control_net_guidance_start"), confirm=confirm(float)),
        AxisOption("[ControlNet] Guidance End", identity, apply_field("control_net_guidance_end"), confirm=confirm(float)),
        AxisOption("[ControlNet] Resize Mode", identity, apply_field("control_net_resize_mode"), confirm=confirm("resize_mode"), choices=choices_resize_mode),
        AxisOption("[ControlNet] Preprocessor", identity, apply_field("control_net_module"), confirm=confirm("preprocessor"), choices=choices_preprocessor),
        AxisOption("[ControlNet] Pre Resolution", identity, apply_field("control_net_pres"), confirm=confirm(int)),
        AxisOption("[ControlNet] Pre Threshold A", identity, apply_field("control_net_pthr_a"), confirm=confirm(float)),
        AxisOption("[ControlNet] Pre Threshold B", identity, apply_field("control_net_pthr_b"), confirm=confirm(float)),
    ]

    xyz_grid.axis_options.extend(extra_axis_options)


def run():
    if xyz_grid := find_module("xyz_grid.py, xy_grid.py"):
        add_axis_options(xyz_grid)


if not import_error:
    run()
