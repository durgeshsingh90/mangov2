#
# Todo: rename the tool to PyJsonUtils
#
class JsonObjUtils:

    @staticmethod
    def get_paths(json_obj, current_path='', value_filter='ALL'):
        paths = []

        if isinstance(json_obj, dict):
            for key, value in json_obj.items():
                next_path = f"{current_path}.{key}" if current_path else key
                paths.extend(JsonObjUtils.get_paths(value, next_path, value_filter))
        elif isinstance(json_obj, list):
            for i, item in enumerate(json_obj):
                next_path = f"{current_path}[{i}]"
                paths.extend(JsonObjUtils.get_paths(item, next_path, value_filter))
        else:
            if (
                    (value_filter == 'ALL') or
                    (value_filter == 'EMPTY_ONLY' and json_obj in [None, ""]) or
                    (value_filter == 'NON_EMPTY_ONLY' and json_obj not in [None, ""])
            ):
                paths.append(current_path)

        return paths

    @staticmethod
    def path_list_2_path_str(path_list, use_double_quotes=True, range_allowed=False):
        path_str = ""
        path_str_before_range = None
        path_str_after_range = None
        path_str_without_range = None

        for path_item in path_list:
            if isinstance(path_item, str):
                if use_double_quotes:
                    path_str = path_str + f'["{path_item}"]'
                else:
                    path_str = path_str + f"['{path_item}']"
            elif isinstance(path_item, int):
                path_str = path_str + f'[{path_item}]'
            elif isinstance(path_item, list) and range_allowed and path_item == path_list[-1] and len(path_item) == 2:
                path_str_without_range = path_str
                path_str_before_range = path_str
                path_str_after_range = path_str

                path_str = path_str + '['

                if path_item[0] is not None:
                    path_str = path_str + f'{path_item[0]}'
                    path_str_before_range = path_str_before_range + f"[:{path_item[0]}]"
                else:
                    path_str_before_range = None

                path_str = path_str + ':'

                if path_item[1] is not None:
                    path_str = path_str + f'{path_item[1]}'
                    path_str_after_range = path_str_after_range + f"[{path_item[1]}:]"
                else:
                    path_str_after_range = None

                path_str = path_str + ']'

            else:
                return None

        if range_allowed:
            return path_str, path_str_without_range, path_str_before_range, path_str_after_range
        else:
            return path_str

    @staticmethod
    def path_str_2_path_list(path_str):
        if path_str == "":
            return []

        path_list = eval(path_str.replace('][', ','))
        return path_list

    @staticmethod
    def get_item(root, path_list):
        path_str, _, _, _ = JsonObjUtils.path_list_2_path_str(path_list, range_allowed=True)
        if path_str is not None:
            try:
                return eval("root" + path_str)
            except (KeyError, IndexError, TypeError):
                pass

        return None

    @staticmethod
    def item_exist(root, path_list):
        path_str, _, _, _ = JsonObjUtils.path_list_2_path_str(path_list, range_allowed=True)
        if path_str is not None:
            try:
                _ = eval("root" + path_str)
                return True
            except (KeyError, IndexError, TypeError):
                pass

        return False

    @staticmethod
    def create_item(root, path_list):
        tmp_path_list = []
        for path_item in path_list:
            tmp_path_list.append(path_item)
            if not JsonObjUtils.item_exist(root, tmp_path_list):
                if isinstance(path_item, str):
                    item = JsonObjUtils.get_item(root, tmp_path_list[:-1])
                    if isinstance(item, dict):
                        item[path_item] = None
                    elif item is None:
                        item = {path_item: None}
                    else:
                        return False

                elif isinstance(path_item, int):
                    item = JsonObjUtils.get_item(root, tmp_path_list[:-1])
                    if isinstance(item, list):
                        item.extend([None] * (path_item + 1 - len(item)))
                    elif item is None:
                        item = [None] * (path_item + 1)
                    else:
                        return False
                else:
                    return False

                JsonObjUtils.set_item(root, tmp_path_list[:-1], item)
        return True

    @staticmethod
    def set_item(root, path_list, value):
        path_str_with_range, path_str_without_range, path_str_before_range,  path_str_after_range = \
            JsonObjUtils.path_list_2_path_str(path_list, range_allowed=True)

        if path_str_with_range is not None:
            try:
                #
                # No range
                #
                if path_str_before_range is None and path_str_after_range is None and path_str_without_range is None:
                    exec("root" + path_str_with_range + " = value")
                    return True

                #
                # [:]
                #
                if path_str_before_range is None and path_str_after_range is None:
                    exec("root" + path_str_without_range + " = value")
                    return True

                locals_dict = {"root": root}
                if path_str_before_range is not None:
                    exec("new_value = root" + path_str_before_range, globals(), locals_dict)
                    new_value = locals_dict["new_value"]
                    new_value = new_value + value
                else:
                    new_value = value

                if path_str_after_range is not None:
                    locals_dict["new_value"] = new_value
                    exec("new_value = new_value + root" + path_str_after_range, globals(), locals_dict)
                    new_value = locals_dict["new_value"]

                exec("root" + path_str_without_range + "= new_value")
                return True
            except (KeyError, IndexError, TypeError):
                pass

        return False

    @staticmethod
    def remove_item(root, path_list):
        path_str = JsonObjUtils.path_list_2_path_str(path_list)
        if path_str:
            try:
                exec("del root" + path_str)
                return True
            except (KeyError, IndexError, TypeError):
                pass

            return False

    @staticmethod
    def get_items(root, paths_list):
        ret_list = []
        for path_list in paths_list:
            ret_list.append(JsonObjUtils.get_item(root, path_list))

        return ret_list

    @staticmethod
    def evaluate_conds(json_obj, cond_list):
        if not cond_list:
            return True

        log_stat_list = []
        for cond_item in cond_list:

            if isinstance(cond_item, str):
                log_oper = cond_item.lower()
                if log_oper not in ["or", "and"]:
                    raise ValueError("Only 'and' or 'or' is allowed as operator in condition list ")

                if not log_stat_list:
                    raise ValueError("Logical operator not allowed as first item in condition list")

                if isinstance(log_stat_list[-1], str):
                    raise ValueError("Logical operand missing")

                log_stat_list.append(log_oper)
            else:
                #
                #   Last item in list is True/False which means that logical operator is  missing.
                #   Add the default 'and'
                #
                if log_stat_list and isinstance(log_stat_list[-1], bool):
                    log_stat_list.append("and")

                if isinstance(cond_item, list):
                    log_stat_list.append(JsonObjUtils.evaluate_conds(json_obj, cond_item))
                elif isinstance(cond_item, dict):
                    log_stat_list.append(JsonObjUtils.evaluate_cond(json_obj, cond_item))
                else:
                    raise ValueError("Only 'list', 'dict' or 'str' is allowed as item in condition list")

        if isinstance(log_stat_list[-1], str):
            raise ValueError("Logical operator not allowed as last item in condition list")

        eval_str = ""
        for item in log_stat_list:
            eval_str = eval_str + " " + str(item)

        return eval(eval_str)

    @staticmethod
    def evaluate_cond(json_obj, cond):
        value = None
        if JsonObjUtils.item_exist(json_obj, cond["loc_key"]):
            value = JsonObjUtils.get_item(json_obj, cond["loc_key"])

        if cond["operator"] == "==":
            if not (value == cond["value"]):
                return False
        elif cond["operator"] == "<":
            if not (value < cond["value"]):
                return False
        elif cond["operator"] == ">":
            if not (value > cond["value"]):
                return False
        elif cond["operator"] == "<>" or cond["operator"] == "!=":
            if not (value != cond["value"]):
                return False
        elif cond["operator"].upper() == "STARTSWITH" or cond["operator"].upper() == "STARTS":
            if isinstance(value, str):
                if not (value.startswith(cond["value"])):
                    return False
            else:
                return False
        elif cond["operator"].upper() == "ENDSWITH" or cond["operator"].upper() == "ENDS":
            if isinstance(value, str):
                if not (value.endswith(cond["value"])):
                    return False
            else:
                return False
        elif cond["operator"].upper() == "NOT STARTSWITH" or cond["operator"].upper() == "NOT STARTS":
            if isinstance(value, str):
                if value.startswith(cond["value"]):
                    return False
            else:
                return False
        elif cond["operator"].upper() == "NOT ENDSWITH" or cond["operator"].upper() == "NOT ENDS":
            if isinstance(value, str):
                if value.endswith(cond["value"]):
                    return False
            else:
                return False
        elif cond["operator"].upper() == "IN":
            if not (value in cond["value"]):
                return False
        elif cond["operator"].upper() == "NOT IN":
            if value in cond["value"]:
                return False
        elif cond["operator"].upper() == "CONTAINS":
            if isinstance(value, str) or isinstance(value, dict) or isinstance(value, list):
                if not (cond["value"] in value):
                    return False
            else:
                return False
        elif cond["operator"].upper() == "IS":
            cond_val = cond["value"].upper()
            if cond_val == "ALPHA":
                if not str(value).isalpha():
                    return False
            elif cond_val == "DIGIT":
                if not str(value).isdigit():
                    return False
            elif cond_val == "NUMERIC":
                if not str(value).isnumeric():
                    return False
            elif cond_val in ["ALNUM", "APHANUM", "ALPHANUMERIC"]:
                if not str(value).isalnum():
                    return False
            elif cond_val == "SPACE":
                if not str(value).isspace():
                    return False
            elif cond_val == "LOWER":
                if not str(value).islower():
                    return False
            elif cond_val == "UPPER":
                if not str(value).isupper():
                    return False
            else:
                return False

        elif cond["operator"].upper() == "IS NOT":
            cond_val = cond["value"].upper()
            if cond_val == "ALPHA":
                if str(value).isalpha():
                    return False
            elif cond_val == "DIGIT":
                if str(value).isdigit():
                    return False
            elif cond_val == "NUMERIC":
                if str(value).isnumeric():
                    return False
            elif cond_val in ["ALNUM", "APHANUM", "ALPHANUMERIC"]:
                if str(value).isalnum():
                    return False
            elif cond_val == "SPACE":
                if str(value).isspace():
                    return False
            elif cond_val == "LOWER":
                if str(value).islower():
                    return False
            elif cond_val == "UPPER":
                if str(value).isupper():
                    return False
            else:
                return False

        return True
