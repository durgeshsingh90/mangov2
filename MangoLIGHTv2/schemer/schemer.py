from os.path import join, dirname, isdir
from os import makedirs
from abc import abstractmethod, ABC
from json.decoder import  JSONDecodeError
from json import load
from re import compile
from codecs import  encode, decode
from bitstring import BitArray, CreationError
from logging import INFO, WARNING, ERROR, DEBUG
from xml.sax.saxutils import escape, unescape
#from numpy import ceil, base_repr
from copy import copy

from logging_ext import LoggerMgr
from json_obj_utils import JsonObjUtils

__all__ = ["Schemer", "Schema", "SchemerException", "NotAbleToCreateError", "NotAbleToBuildError",
           "NotAbleToParseError", "NotAbleToProcessConfig"]


def add_debug_log_msg(func):
    def decorator(*args, **kwargs):

        if isinstance(args[0], Base):
            schemer = args[0]._schemer
        else:
            schemer = args[2]

        LoggerMgr.log(schemer._logger_name, DEBUG, f"FUNC ENTRY: loc={schemer._loc_key}, func={func}, args={args}, kwargs={kwargs}")
        ret_val = func(*args, **kwargs)
        LoggerMgr.log(schemer._logger_name, DEBUG, f"FUNC EXIT: loc={schemer._loc_key}, func={func} return={ret_val}")

        return ret_val
    return decorator


def check_input_to_build(instance):
    def decorator_wrap(method):
        def decorator(*args, **kwargs):

            if not isinstance(args[1], instance):
                raise NotAbleToBuildError(f"{instance.__name__} expected intead of {type(args[1]).__name__}",
                                          args[0].__class__,
                                          args[0]._schemer)

            else:
                return method(*args, **kwargs)
        return decorator
    return decorator_wrap

#
#   Todo: refactor SchemerException names (add the Error suffix)
#
class SchemerException(Exception):
    def __init__(self, message, cls, schemer):
        self._class_name = cls.__name__
        self._message = message
        self._schemer = schemer
        LoggerMgr.log(self._schemer._logger_name, ERROR, f"Exception raised: {self.get_full_message()}")

    def __str__(self):
        return self.get_full_message()

    @abstractmethod
    def get_full_message(self):
        pass


class NotAbleToProcessConfig(SchemerException):
    def get_full_message(self):
        return f"Not able to process config: {self._message}"


class NotAbleToCreateError(SchemerException):
    def get_full_message(self):
        return f"Not able to create {self._schemer._loc_key}. Error occured in {self._class_name}: {self._message}."

    def get_loc_key(self):
        return self._schemer._loc_key


class NotAbleToParseError(SchemerException):
    def get_full_message(self):
        return f"Not able to parse {self._schemer._loc_key}. Error occured in {self._class_name}: {self._message}."

    def get_loc_key(self):
        return self._schemer._loc_key


class NotAbleToBuildError(SchemerException):
    def get_full_message(self):
        return f"Not able to build {self._schemer._loc_key}. Error occured in {self._class_name}: {self._message}."

    def get_loc_key(self):
        return self._schemer._loc_key


class InvalidTypeId(SchemerException):
    def get_full_message(self):
        return f"{self._message} in {self._schemer._loc_key}. Error occured in {self._class_name}"

    def get_loc_key(self):
        return self._schemer._loc_key



class Base(ABC):
    @classmethod
    def from_val(cls, val, schemer, **kwargs):
        if val is None:
            def from_none_wrapper(val, schemer, **kwargs):
                return cls.from_none(schemer, **kwargs)
            method = from_none_wrapper
        elif isinstance(val, dict):
            method = cls.from_dict
        elif isinstance(val, list):
            method = cls.from_list
        elif isinstance(val, str):
            method = cls.from_str
        elif isinstance(val, int):
            method = cls.from_int
        elif isinstance(val, float):
            method = cls.from_float
        else:
            raise TypeError(f'unsupported value type: {type(val)}')
        instance = method(val, schemer,  **kwargs)
        return instance

    @classmethod
    def from_none(cls, schemer, **kwargs):
        raise TypeError('none not supported')

    @classmethod
    def from_dict(cls, in_arg_dict, schemer, **kwargs):
        raise TypeError('dict not supported')

    @classmethod
    def from_list(cls, in_arg_list, schemer, **kwargs):
        raise TypeError('list not supported')

    @classmethod
    def from_str(cls, in_arg_str, schemer, **kwargs):
        raise TypeError('str not supported')

    @classmethod
    def from_int(cls, in_arg_int, schemer, **kwargs):
        raise TypeError('int not supported')

    @classmethod
    def from_float(cls, in_arg_float,  schemer, **kwargs):
        raise TypeError('float not supported')

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')


class Proc(Base):
    _special_attrs = {'type', 'len', 'unit',  'subtype', 'base', 'escape_xml'}

    @classmethod
    def from_none(cls, schemer, **kwargs):
        dict_val = {}
        fields = cls.from_dict(dict_val, schemer,  **kwargs)
        return fields

    @classmethod
    def from_dict(cls, dict_val, schemer, **kwargs):
        spec = {}
        for name, val in dict_val.items():
            if name in cls._special_attrs:
                if name in kwargs:
                    raise ValueError(f'conflicting {name} specifiers')
                kwargs[name] = val
            else:
                spec[name] = val

        try:
            typeid = kwargs.pop('type')

        except KeyError:
            try:
                typeid = getattr(cls, '__default_typeid__')
            except AttributeError:
                raise KeyError('missing type specifier') from None
            proc = cls._route(typeid, spec, schemer, **kwargs)
        else:
            try:
                proc = cls._route(typeid, spec, schemer, **kwargs)
            except InvalidTypeId as e:
                kwargs['type'] = typeid
                try:
                    typeid = getattr(cls, '__default_typeid__')
                except AttributeError:
                    raise e
                try:
                    proc = cls._route(typeid, spec, schemer, **kwargs)
                except InvalidTypeId:
                    raise e

        return proc

    @classmethod
    def _route(cls, typeid, spec, schemer, **kwargs):
        try:
            cls_typeid = getattr(cls, '__typeid__')
        except AttributeError:
            pass
        else:

            if typeid == cls_typeid:

                proc = cls.create(spec, schemer, **kwargs)
                return proc
        for subclass in cls.__subclasses__():

            try:
                proc = subclass._route(typeid, spec, schemer, **kwargs)
                return proc
            except InvalidTypeId:
                pass

        raise InvalidTypeId(f'Type id {typeid} not found', cls, schemer)


class NodeProc(Proc):
    __default_typeid__ = 'text'

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')


class SchemaNodeProc(NodeProc):
    __typeid__ = 'schema'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        len_proc = LenProc.from_val(kwargs.pop('len', None), schemer, **kwargs)

        schema = spec["schema"]
        msg_type = spec.get("msg_type", None)
        return cls(len_proc, schema, msg_type, schemer)

    def __init__(self, len_proc, schema, msg_type, schemer):
        self._len_proc = len_proc
        self._schema = schema
        self._msg_type = msg_type

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):

        current_loc_key = self._schemer._loc_key[:]
        anything_buff, remainder = self._len_proc.parse(msg, **kwargs)
        anything, _ = self._schemer.parse(anything_buff, self._schema, self._msg_type)
        self._schemer._loc_key = current_loc_key

        return anything, remainder

    @add_debug_log_msg
    def build(self, anything, **kwargs):


        current_loc_key = self._schemer._loc_key[:]
        anything_buff = self._schemer.build(anything, self._schema, self._msg_type)
        self._schemer._loc_key = current_loc_key
        return self._len_proc.build(anything_buff, **kwargs)


class TxtNodeProc(NodeProc):
    __typeid__ = 'text'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        str_proc = StrProc.from_val(spec.get('value', None), schemer, **kwargs)
        return cls(str_proc, schemer)

    def __init__(self, str_proc, schemer):
        self._str_proc = str_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        return self._str_proc.parse(msg, **kwargs)

    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, text, **kwargs):
        return self._str_proc.build(text, **kwargs)


class LenTagValNodeProc(NodeProc):
    __typeid__ = 'len_tag_val'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        len_proc = LenProc.from_val(kwargs.pop('len', None), schemer, **kwargs)

        if isinstance(len_proc, StaticLenProc):
            raise NotAbleToCreateError('"len"={"type":"static"} is not supported', cls, schemer)

        tag_id = spec.get("tag_id", {"type": "text", "len": 2})
        tag_val = spec.get("tag_val", {"type": "text"})
        tag_id_val_len = spec.get('tag_id_val_len', 2)
        tags =  spec.get('tags', {})
        id_mapping =  spec.get('id_mapping', {})

        if "len" in tag_val:
            if not isinstance(LenProc.from_val(tag_val["len"], schemer, **kwargs), RemainderLenProc):
                raise NotAbleToCreateError('"len" is not supported in tag_val', cls, schemer)

        ltv = LenTagVal.from_val(
            {
                "tag_id": tag_id,
                "tag_val": tag_val,
                "tag_id_val_len": tag_id_val_len,
                "tags": tags,
                "id_mapping": id_mapping
            },
            schemer,
            **kwargs)

        return cls(len_proc, ltv, schemer)

    def __init__(self, len_proc, ltv, schemer):
        self._len_proc = len_proc
        self._ltv = ltv

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        ltv_buff, remainder = self._len_proc.parse(msg, **kwargs)
        ltv_dict, _ = self._ltv.parse(ltv_buff, **kwargs)
        return ltv_dict, remainder

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, ltv_dict, **kwargs):
        ltv_buff = self._ltv.build(ltv_dict)
        return self._len_proc.build(ltv_buff, **kwargs)

class TagLenValNodeProc(NodeProc):
    __typeid__ = 'tag_len_val'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        len_proc = LenProc.from_val(kwargs.pop('len', None), schemer, **kwargs)

        if isinstance(len_proc, StaticLenProc):
            raise NotAbleToCreateError('"len"={"type":"static"} is not supported', cls, schemer)

        tag_id = spec.get("tag_id", {"type": "text", "len": 2})
        tag_val = spec.get("tag_val", {"type": "text", "len": {"type": "indicator", "len": 3 }})
        tags    = spec.get('tags', {})
        id_mapping = spec.get('id_mapping', {})

        tlv = TagLenVal.from_val(
            {
                "tag_id": tag_id,
                "tag_val": tag_val,
                "tags": tags,
                "id_mapping": id_mapping
            },
            schemer,
            **kwargs)

        return cls(len_proc, tlv, schemer)

    def __init__(self, len_proc, tlv, schemer):
        self._len_proc = len_proc
        self._tlv = tlv

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        tlv_buff, remainder = self._len_proc.parse(msg, **kwargs)
        tlv_dict, _ = self._tlv.parse(tlv_buff, **kwargs)
        return tlv_dict, remainder

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, tlv_dict, **kwargs):
        tlv_buff = self._tlv.build(tlv_dict)
        return self._len_proc.build(tlv_buff, **kwargs)


class TknsNodeProc(NodeProc):
    __typeid__ = 'tokens'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        len_proc = LenProc.from_val(kwargs.pop('len', None), schemer, **kwargs)

        if isinstance(len_proc, StaticLenProc):
            raise NotAbleToCreateError('"len"={"type":"static"} is not supported', cls, schemer)

        escape_xml = kwargs.pop('escape_xml', False)

        tkn_hdr_len = 12

        tkns_hdr_proc = StrProc.from_val({"len": tkn_hdr_len}, schemer, **kwargs)

        tag_id = spec.get("tkn_id", {"type": "text", "len": 4})
        tag_val = spec.get("tkn_val", {"type": "text", "len": {"type": "indicator", "len": 5, "ignore": 1, "ignore_byte": b" "}})
        tags = spec.get('tkns', {})
        id_mapping = spec.get('id_mapping', {})

        tlv = TagLenVal.from_val(
            {
                "tag_id": tag_id,
                "tag_val": tag_val,
                "tags": tags,
                "id_mapping": id_mapping
            },
            schemer,
            **kwargs)

        return cls(len_proc, tkns_hdr_proc, tlv, escape_xml, schemer)

    def __init__(self, len_proc, tkns_hdr_proc, tlv, escape_xml, schemer):
        self._len_proc = len_proc
        self._escape_xml = escape_xml
        self._tkns_hdr_proc = tkns_hdr_proc
        self._tlv = tlv

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        tkns_buff, remainder = self._len_proc.parse(msg, **kwargs)
        if self._escape_xml:
            try:
                tkns_buff = unescape(tkns_buff.decode(encoding="latin-1"), entities={"&quot;": '"'}).encode(encoding="latin-1")
            except Exception as e:
                raise NotAbleToParseError(str(e), self.__class__, self._schemer)

        _, tkns_buff = self._tkns_hdr_proc.parse(tkns_buff, **kwargs)
        tkns_dict, _ = self._tlv.parse(tkns_buff, **kwargs)

        return tkns_dict, remainder

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, tkns_dict, **kwargs):
        tkns_buff = self._tlv.build(tkns_dict, **kwargs)
        tkn_count = str(len(tkns_dict) + 1).zfill(5)
        tkn_len = str(len(tkns_buff) + 12).zfill(5)
        eye_catcher = "&"
        tkns_hdr_buff = self._tkns_hdr_proc.build(eye_catcher + " " + tkn_count + tkn_len, **kwargs)

        tkns_buff = tkns_hdr_buff + tkns_buff

        if self._escape_xml:
            try:
                tkns_buff = escape(tkns_buff.decode(encoding="latin-1"), entities={'"': '&quot;'}).encode(encoding="latin-1")
            except Exception as e:
                raise NotAbleToBuildError(str(e), self.__class__, self._schemer)

        return self._len_proc.build(tkns_buff, **kwargs)


class DelimSepFldsNodeProc(NodeProc):
    __typeid__ = 'delimiter_separated_fields'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        len_proc = LenProc.from_val(kwargs.pop('len', None), schemer, **kwargs)
        if isinstance(len_proc, StaticLenProc):
            raise NotAbleToCreateError('"len"={"type":"static"} is not supported', cls, schemer)

        try:
            delimiter = spec.get("delimiter")
        except KeyError:
            raise NotAbleToCreateError('"delimiter is mandatroy', cls, schemer)

        fld_len_proc = LenProc.from_val({"type": "delimiter", "consume_delimiter": True, "delimiter": delimiter},
                                        schemer,
                                        **kwargs)

        fld_id_proc = None
        schemer._loc_key.append("fld_id")

        if "fld_id" in spec:
            fld_id_proc = NodeProc.from_val(spec['fld_id'], schemer, **kwargs)

        fld_val_proc = NodeProc.from_val(spec.get('fld_val', {"type": "text"}), schemer, **kwargs)

        schemer._loc_key.pop()

        flds_proc_dict = {}
        for fld_id, node_proc_val in spec.get("fields", {}).items():
            schemer._loc_key.append(fld_id)
            flds_proc_dict[fld_id] = NodeProc.from_val(node_proc_val, schemer, **kwargs)
            schemer._loc_key.pop()

        starts_with_sep = spec.get('starts_with_sep', False)
        ends_with_sep = spec.get('ends_with_sep', False)
        id_mapping_dict = spec.get('id_mapping', {})

        return cls(len_proc,
                   fld_len_proc,
                   fld_id_proc,
                   fld_val_proc,
                   flds_proc_dict,
                   starts_with_sep,
                   ends_with_sep,
                   id_mapping_dict,
                   schemer)

    def __init__(self,
                 len_proc,
                 fld_len_proc,
                 fld_id_proc,
                 fld_val_proc,
                 flds_proc_dict,
                 starts_with_sep,
                 ends_with_sep,
                 id_mapping_dict,
                 schemer):

        self._len_proc = len_proc
        self._fld_len_proc = fld_len_proc
        self._fld_id_proc = fld_id_proc
        self._fld_val_proc = fld_val_proc
        self._flds_proc_dict = flds_proc_dict
        self._starts_with_sep = starts_with_sep
        self._ends_with_sep = ends_with_sep
        self._id_mapping_dict = id_mapping_dict

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):

        flds_buff, remainder = self._len_proc.parse(msg, **kwargs)

        if self._starts_with_sep:
            flds_buff = flds_buff[len(self._fld_len_proc._delimiter):]

        flds_dict = {}

        while flds_buff:
            fld_buff, flds_buff = self._fld_len_proc.parse(flds_buff, **kwargs)
            if self._fld_id_proc:
                fld_id, fld_buff = self._fld_id_proc.parse(fld_buff, **kwargs)
            else:
                fld_id = str(len(flds_dict))

            self._schemer._loc_key.append(fld_id)
            if fld_id in self._flds_proc_dict:
                fld_val, _ = self._flds_proc_dict[fld_id].parse(fld_buff, **kwargs)
            else:
                fld_val, _ = self._fld_val_proc.parse(fld_buff, **kwargs)
            self._schemer._loc_key.pop()

            if fld_id in self._id_mapping_dict:
                fld_id = self._id_mapping_dict[fld_id]
            flds_dict[fld_id] = fld_val

        #
        #   compress
        #
        empty_keys = [k for k, v in flds_dict.items() if not v]
        for k in empty_keys:
            del flds_dict[k]

        return flds_dict, remainder

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, flds_dict, **kwargs):
        id_mapping = {value: key for key, value in self._id_mapping_dict.items()}

        flds_buff = b""
        last_id = None
        for fld_id, fld_val in flds_dict.items():
            if fld_id in id_mapping:
                fld_id = id_mapping[fld_id]

            self._schemer._loc_key.append(fld_id)
            fld_buff = b""

            id_diff = None
            if self._fld_id_proc:
                fld_buff = fld_buff + self._fld_id_proc.build(fld_id, **kwargs)
            else:
                if last_id is not None:
                    id_diff = int(fld_id) - int(last_id)
                last_id = fld_id

            if fld_id in self._flds_proc_dict:
                fld_buff = fld_buff + self._flds_proc_dict[fld_id].build(fld_val, **kwargs)
            else:
                fld_buff = fld_buff + self._fld_val_proc.build(fld_val, **kwargs)

            #
            #   de-compress
            #
            if id_diff is not None and id_diff > 1:
                for i in range(id_diff-1):
                    flds_buff = flds_buff + self._fld_len_proc.build(b"", **kwargs)

            flds_buff = flds_buff + self._fld_len_proc.build(fld_buff, **kwargs)
            self._schemer._loc_key.pop()

        if not self._ends_with_sep:
            flds_buff = flds_buff[:-len(self._fld_len_proc._delimiter)]

        if self._starts_with_sep:
            flds_buff = self._fld_len_proc._delimiter + flds_buff

        return self._len_proc.build(flds_buff, **kwargs)


class NumNodeProc(NodeProc):
    __typeid__ = 'numeric'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        int_proc = IntProc.from_val(spec.get('value', None), schemer, **kwargs)
        return cls(int_proc, schemer)

    def __init__(self, int_proc, schemer):
        self._int_proc = int_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        return self._int_proc.parse(msg, **kwargs)

    @check_input_to_build(int)
    @add_debug_log_msg
    def build(self, number, **kwargs):
        return self._int_proc.build(number, **kwargs)


class SeqNodeProc(NodeProc):
    __typeid__ = 'sequence'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        len_proc = None

        if 'len' in kwargs:
            len_proc = LenProc.from_val(kwargs.pop('len'), schemer, **kwargs)
            if isinstance(len_proc, StaticLenProc):
                raise NotAbleToCreateError('"len"={"type":"static"} is not supported', cls, schemer)

        fields = Fields.from_val(spec.get('fields', None), schemer, **kwargs)

        return cls(fields, len_proc, schemer)

    def __init__(self, fields, len_proc, schemer):
        self._fields = fields
        self._len_proc = len_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        bitmap = [True] * len(self._fields._children_dict)
        if self._len_proc:
            val, msg = self._len_proc.parse(msg, **kwargs)

            val, _ = self._fields.parse(val, bitmap, **kwargs)
            return val, msg
        else:
            return self._fields.parse(msg, bitmap, **kwargs)

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, seq_dict, **kwargs):
        if seq_dict is None:
            return b""

        raw_msg, bitmap = self._fields.build(seq_dict, **kwargs)

        seq_end_found = False
        for bit in bitmap:
            if not bit:
                seq_end_found = True

            if seq_end_found and bit:
                raise NotAbleToBuildError('mandatory field missing', self.__class__, self._schemer)

        if self._len_proc:
            return self._len_proc.build(raw_msg, **kwargs)
        else:
            return raw_msg


class BitmapBlocksNodeProc(NodeProc):
    __typeid__ = 'bitmap_blocks'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        len_proc = None
        if "len" in kwargs:
            len_proc = LenProc.from_val(kwargs.pop('len'), schemer, **kwargs)
            if isinstance(len_proc, StaticLenProc):
                raise NotAbleToCreateError('"len"={"type":"static"} is not supported', cls, schemer)

        blocks = Blocks.from_val(spec.get('blocks', None), schemer, **kwargs)
        return cls(blocks, len_proc, schemer)

    def __init__(self, blocks, len_proc, schemer):
        self._blocks = blocks
        self._len_proc = len_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if self._len_proc:
            bitmap_blocks_buff, msg = self._len_proc.parse(msg, **kwargs)
            bitmap_blocks_dict, _ = self._blocks.parse(bitmap_blocks_buff, **kwargs)
            return bitmap_blocks_dict, msg
        else:
            return  self._blocks.parse(msg, **kwargs)

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, bitmap_blocks_dict, **kwargs):
        if bitmap_blocks_dict is None:
            return b""

        raw_msg = self._blocks.build(bitmap_blocks_dict, **kwargs)
        if self._len_proc:
            return self._len_proc.build(raw_msg, **kwargs)
        else:
            return raw_msg


class LenProc(Proc):
    __default_typeid__ = 'remainder'
    __default_unit__ = 'byte'

    @classmethod
    @add_debug_log_msg
    def from_int(cls, int_val, schemer, **kwargs):
        spec = {
            'type': 'static',
            'value': int_val
        }

        len_proc = cls.from_dict(spec, schemer, **kwargs)
        return len_proc

    @classmethod
    @add_debug_log_msg
    def from_str(cls, str_val, schemer, **kwargs):

        indicator_len_re = compile('(?P<len_count>l+)var')
        match = indicator_len_re.fullmatch(str_val)
        if match:
            return cls.from_dict({'type': 'indicator', 'len': len(match['len_count'])}, schemer, **kwargs)

        indicator_len_re = compile('(?P<len_count>l+)var_ascii')
        match = indicator_len_re.fullmatch(str_val)
        if match:
            return cls.from_dict({'type': 'indicator', 'len': len(match['len_count'])}, schemer, **kwargs)

        indicator_len_re = compile('(?P<len_count>l+)var_bcd')
        match = indicator_len_re.fullmatch(str_val)
        if match:
            return cls.from_dict({'type': 'indicator', 'len': len(match['len_count']), 'value': 'bcd'},
                                 schemer,
                                 **kwargs)

        indicator_len_re = compile('(?P<len_count>l+)var_binary')
        match = indicator_len_re.fullmatch(str_val)
        if match:
            return cls.from_dict({'type': 'indicator', 'len': len(match['len_count']), 'value': 'binary'},
                                 schemer,
                                 **kwargs)

        indicator_len_re = compile('(?P<len_count>l+)var_ebcdic')
        match = indicator_len_re.fullmatch(str_val)
        if match:
            return cls.from_dict({'type': 'indicator', 'len': len(match['len_count']), 'value': 'ebcdic'},
                                 schemer,
                                 **kwargs)

        raise NotAbleToCreateError(f'"len"="{str_val}" not supported', cls, schemer)


class StaticLenProc(LenProc):
    __typeid__ = 'static'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        value = int(spec.get('value', 0))
        
        unit = kwargs.pop('unit', getattr(cls, '__default_unit__'))

        alignment = kwargs["alignment"]
        pad_char = kwargs["pad_char"]

        return cls(value, unit, alignment, pad_char, schemer)

    def __init__(self, value, unit, alignment, pad_char, schemer):
        self._value = value
        self._unit = unit
        self._alignment = alignment
        self._pad_char = pad_char

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            len_val = self._value

            if self._unit == "nibble":
                len_val = len_val * 2

            if len(msg) < len_val:
                raise NotAbleToParseError(f"buffer len: {len(msg)}, expected buffer len: {len_val}",
                                          self.__class__,
                                          self._schemer)
            return msg[:len_val], msg[len_val:]

        else:
            return b"", msg

    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):
        len_val = self._value
        if self._unit == "nibble":
            len_val = len_val / 2

            if len_val.is_integer():
                len_val = int(len_val)
            else:
                len_val = int(len_val) + 1

        len_diff = len_val - len(bytes_buff)

        if len_diff < 0:
            bytes_buff = bytes_buff[:len_val]

        if len_diff > 0:
            if self._alignment.upper() == "RIGHT":
                bytes_buff = self._pad_char * len_diff + bytes_buff
            if self._alignment.upper() == "LEFT":
                bytes_buff = bytes_buff + self._pad_char * len_diff

        return bytes_buff


class RemainderLenProc(LenProc):
    __typeid__ = 'remainder'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        return cls(schemer)

    def __init__(self, schemer):
        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            return msg, None
        else:
            return b"", None

    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):
        return bytes_buff


class DelimLenProc(LenProc):
    __typeid__ = 'delimiter'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        try:
            delimiter = spec['delimiter']
            consume_delimiter = spec.get('consume_delimiter', False)
            if isinstance(delimiter, bytes):
                pass
            if isinstance(delimiter, int):
                try:
                    delimiter = delimiter.to_bytes(1, byteorder='big')
                except OverflowError:
                    raise NotAbleToCreateError('"delimiter" out of range', cls, schemer)

            if isinstance(delimiter, str):
                delimiter = delimiter.encode(encoding="latin-1")

        except KeyError:
            raise NotAbleToCreateError('"delimiter" is mandatory', cls, schemer)

        return cls(delimiter, consume_delimiter, schemer)

    def __init__(self, delimiter, consume_delimiter, schemer):
        self._delimiter = delimiter
        self._consume_delimiter = consume_delimiter

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            delimiter_pos = msg.find(self._delimiter)
            if delimiter_pos > -1:
                if self._consume_delimiter:
                    return msg[:delimiter_pos], msg[delimiter_pos + len(self._delimiter):]
                else:
                    return msg[:delimiter_pos], msg[delimiter_pos:]
            else:
                return msg, None
        else:
            return b"", None

    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):
        if self._consume_delimiter:
            bytes_buff = bytes_buff + self._delimiter

        return bytes_buff


class IndicatorLenProc(LenProc):
    __typeid__ = 'indicator'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        unit = kwargs.pop('unit', getattr(cls, '__default_unit__'))

        ignore = spec.get('ignore', 0)
        ignore_byte = None

        if ignore:
            try:
                ignore_byte = spec['ignore_byte']
                if isinstance(ignore_byte, bytes):
                    pass
                if isinstance(ignore_byte, int):
                    try:
                        ignore_byte = ignore_byte.to_bytes(1, byteorder='big')
                    except OverflowError:
                        raise NotAbleToCreateError('"ignore_byte" out of range', cls, schemer)

                if isinstance(ignore_byte, str):
                    ignore_byte = ignore_byte.encode(encoding="latin-1")

            except KeyError:
                raise NotAbleToCreateError('"ignore_byte" is mandatory', cls, schemer)

        int_proc = IntProc.from_val(spec.get('value'), schemer, **kwargs)

        return cls(int_proc, unit, ignore, ignore_byte, schemer)

    def __init__(self, int_proc,  unit, ignore, ignore_byte, schemer):
        self._int_proc = int_proc
        self._unit = unit
        self._ignore = ignore
        self._ignore_byte = ignore_byte

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            val, msg = self._int_proc.parse(msg, **kwargs)

            # Todo: we have to indicate somehow that extra half byte is returned (not sure yet how)
            if self._unit == "nibble":
                val = val / 2
                if val.is_integer():
                    val = int(val)
                else:
                    val = int(val) + 1

            if len(msg) < (self._ignore + val):
                raise NotAbleToParseError(f"buffer len: {len(msg)}, expected buffer len: {(self._ignore + val)}",
                                          self.__class__,
                                          self._schemer)

            ret_val = msg[self._ignore:+self._ignore + val], msg[self._ignore + val:]
            return ret_val

        return b"", None

    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):
        bytes_len = len(bytes_buff)

        if bytes_len != 0:
            if self._unit == "nibble":
                bytes_len = bytes_len * 2
                if int(bytes_buff[0]) < 16:
                    # Todo: Not works allways correctly (check also build methodn in StrFromBinProc):
                    #   - for VISA this is fine as in case of nibble left padding by 0 is expected
                    #   - for HPDH does not work as expected as right padding with F is expected
                    bytes_len = bytes_len - 1

        ignore_bytes = b''
        if self._ignore:
            ignore_bytes = self._ignore * self._ignore_byte

        return self._int_proc.build(bytes_len, **kwargs) + ignore_bytes + bytes_buff


class BerTagIdLenProc(LenProc):
    __typeid__ = 'ber_tag_id'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        eight_bits_str_proc = EightBitsStrProc.from_val(spec.get('value'), schemer, **kwargs)

        return cls(eight_bits_str_proc, schemer)

    def __init__(self, eight_bits_str_proc, schemer):
        self._eight_bits_str_proc = eight_bits_str_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            msg_buff = msg
            tag_id_len = 0
            while msg_buff:
                tag_id_8_bits_string, msg_buff = self._eight_bits_str_proc.parse(msg_buff, **kwargs)
                tag_id_len = tag_id_len + 1
                if (tag_id_len == 1 and tag_id_8_bits_string[-5:] != "11111") or \
                   (tag_id_len > 1 and tag_id_8_bits_string[0] != "1"):
                    break

            if not isinstance(self._eight_bits_str_proc, EightBitsStrFromBinaryProc):
                tag_id_len = tag_id_len * 2

            return msg[:tag_id_len], msg[tag_id_len:]

        return b"", None

    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):
        return bytes_buff


class BerTagValLenProc(LenProc):
    __typeid__ = 'ber_tag_val'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        eight_bits_str_proc = EightBitsStrProc.from_val(spec.get('value'), schemer, **kwargs)
        return cls(eight_bits_str_proc, schemer)

    def __init__(self, eight_bits_str_proc, schemer):
        self._eight_bits_str_proc = eight_bits_str_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        try:
            tag_val_len_8_bits_string, msg = self._eight_bits_str_proc.parse(msg, **kwargs)
            if tag_val_len_8_bits_string[0] == "0":
                tag_val_len = int(tag_val_len_8_bits_string[1:], 2)
            else:
                tag_val_len_len = int(tag_val_len_8_bits_string[1:], 2)
                tag_val_len_bitstring = ""
                for i in range(tag_val_len_len):
                    tag_val_len_8_bits_string, msg = self._eight_bits_str_proc.parse(msg, **kwargs)
                    tag_val_len_bitstring = tag_val_len_bitstring + tag_val_len_8_bits_string
                tag_val_len = int(tag_val_len_bitstring, 2)

            if not isinstance(self._eight_bits_str_proc, EightBitsStrFromBinaryProc):
                tag_val_len = tag_val_len * 2
        except IndexError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

        return msg[:tag_val_len], msg[tag_val_len:]


    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):

        bytes_len = len(bytes_buff)
        if not isinstance(self._eight_bits_str_proc, EightBitsStrFromBinaryProc):
            bytes_len = bytes_len // 2
        #
        #   Short Form
        #
        if bytes_len <= 126:
            ret_val = self._eight_bits_str_proc.build(bin(bytes_len)[2:], **kwargs) + bytes_buff
        #
        #   Long Form
        #
        else:
            len_in_hex = hex(bytes_len)[2:]
            if len(len_in_hex) % 2:
                len_in_hex = "0" + len_in_hex
            tag_val_len_len = 0
            ret_val = b''
            for i in range(0, len(len_in_hex), 2):
                ret_val = ret_val + self._eight_bits_str_proc.build(bin(int(len_in_hex[i:i + 2], 16))[2:], **kwargs)
                tag_val_len_len = tag_val_len_len + 1

            ret_val = self._eight_bits_str_proc.build("1" + bin(tag_val_len_len)[2:].zfill(7), **kwargs) + ret_val + bytes_buff

        return ret_val


class EightBitsStrProc(Proc):
    __default_typeid__ = 'binary'

    @classmethod
    @add_debug_log_msg
    def from_str(cls, str_val, schemer, **kwargs):

        if str_val == "ascii":
            spec = {'type': 'ascii'}
        elif str_val == "ebcdic":
            spec = {'type': 'ebcdic'}
        elif str_val == "binary":
            spec = {'type': 'binary'}
        else:
            raise NotAbleToCreateError(f'"type":"{str_val}" not supported', cls, schemer)

        return cls.from_dict(spec, schemer, **kwargs)

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')

    def __init__(self, bytes_proc, schemer):
        self._bytes_proc = bytes_proc

        self._schemer = schemer


class EightBitsStrFromBinaryProc(EightBitsStrProc):
    __typeid__ = 'binary'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        kwargs["pad_char"] = bytes.fromhex("00")
        kwargs["alignment"] = "left"

        bytes_proc = BytesProc.from_val({"len": 1}, schemer, **kwargs)
        return cls(bytes_proc, schemer)

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        eight_bits, msg = self._bytes_proc.parse(msg, **kwargs)
        return BitArray(hex=eight_bits.hex()).bin, msg


    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, eight_bits_str, **kwargs):
        eight_bits_str = eight_bits_str.zfill(8)
        try:
            ret_val = self._bytes_proc.build(bytes.fromhex(BitArray(bin=eight_bits_str).hex), **kwargs)
        except CreationError as e:
            raise NotAbleToBuildError(str(e), self.__class__, self._schemer)

        return ret_val


class EightBitsStrFromAsciiProc(EightBitsStrProc):
    __typeid__ = 'ascii'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        kwargs["pad_char"] = b"0"
        kwargs["alignment"] = "left"

        bytes_proc = BytesProc.from_val({"len": 2}, schemer, **kwargs)
        return cls(bytes_proc, schemer)

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        eight_bits, msg = self._bytes_proc.parse(msg, **kwargs)
        try:
            return BitArray(hex=eight_bits.decode(encoding="latin-1")).bin, msg
        except CreationError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, eight_bits_str, **kwargs):
        eight_bits_str = eight_bits_str.zfill(8)
        try:
            ret_val = self._bytes_proc.build(BitArray(bin=eight_bits_str).hex.encode(encoding="latin-1"),
                                             **kwargs)
        except CreationError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

        return ret_val


class EightBitsStrFromEbcdicProc(EightBitsStrProc):
    __typeid__ = 'ebcdic'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        kwargs["pad_char"] = encode("0", 'cp500')
        kwargs["alignment"] = "left"

        bytes_proc = BytesProc.from_val({"len": 2}, schemer, **kwargs)
        return cls(bytes_proc, schemer)

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        eight_bits, msg = self._bytes_proc.parse(msg, **kwargs)
        try:
            return BitArray(hex=decode(eight_bits, 'cp500')).bin, msg
        except CreationError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, eight_bits_str, **kwargs):
        eight_bits_str = eight_bits_str.zfill(8)
        try:
            ret_val = self._bytes_proc.build(encode(BitArray(bin=eight_bits_str).hex, 'cp500'),
                                             **kwargs)
        except CreationError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

        return ret_val


class IntProc(Proc):
    __default_typeid__ = 'string'
    __default_base__ = 10

    @classmethod
    @add_debug_log_msg
    def from_str(cls, str_val, schemer, **kwargs):

        if str_val == "bcd":
            spec = {'type': 'bcd'}
        elif str_val == "binary":
            spec = {'type': 'binary'}
        elif str_val == "string":
            spec = {'type': 'string'}
        elif str_val == "ascii":
            spec = {'type': 'string', 'value': 'ascii'}
        elif str_val == "ebcdic":
            spec = {'type': 'string', 'value': 'ebcdic'}
        else:
            raise NotAbleToCreateError(f'"type":"{str_val}" not supported', cls, schemer)

        return cls.from_dict(spec, schemer, **kwargs)

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')


def base_repr(number, base=10):
    if base < 2 or base > 36:
        raise ValueError("Base must be between 2 and 36")

    if number == 0:
        return '0'

    digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    sign = '-' if number < 0 else ''
    number = abs(number)
    result = ''

    while number:
        number, remainder = divmod(number, base)
        result = digits[remainder] + result

    return sign + result

class IntFromStrProc(IntProc):
    __typeid__ = 'string'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        base = kwargs.pop('base', getattr(cls, '__default_base__'))

        kwargs["pad_char"] = "0"
        kwargs["alignment"] = "right"

        str_proc = StrProc.from_val(spec.get('value'), schemer,  **kwargs)
        return cls(str_proc, base, schemer)

    def __init__(self, str_proc, base, schemer):
        self._base = base
        self._str_proc = str_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            val, msg = self._str_proc.parse(msg, **kwargs)
            try:
                ret_val = int(val, self._base), msg
            except ValueError as e:
                raise NotAbleToParseError(str(e), self.__class__, self._schemer)
            return ret_val
        else:
            return None, msg

    @check_input_to_build(int)
    @add_debug_log_msg
    def build(self, integer, **kwargs):
        return self._str_proc.build(base_repr(integer, self._base), **kwargs)


class IntFromBinProc(IntProc):
    __typeid__ = 'binary'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        kwargs["pad_char"] = bytes.fromhex("00")
        kwargs["alignment"] = "right"

        bytes_proc = BytesProc.from_val(spec.get('value'), schemer, **kwargs)
        return cls(bytes_proc, schemer)

    def __init__(self, bytes_proc, schemer):
        self._bytes_proc = bytes_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            val, msg = self._bytes_proc.parse(msg, **kwargs)
            return int.from_bytes(val, byteorder='big'), msg
        else:
            return None, msg

    @check_input_to_build(int)
    @add_debug_log_msg
    def build(self, integer, **kwargs):
        byte_len = (integer.bit_length() + 7) // 8
        return self._bytes_proc.build(integer.to_bytes(byte_len, byteorder='big'), **kwargs)



class IntFromBcdProc(IntProc):
    __typeid__ = 'bcd'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer,  **kwargs):

        kwargs["pad_char"] = bytes.fromhex("00")
        kwargs["alignment"] = "right"

        bytes_proc = BytesProc.from_val(spec.get('value'), schemer, **kwargs)
        return cls(bytes_proc, schemer)

    def __init__(self, bytes_proc, schemer):
        self._bytes_proc = bytes_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        if msg:
            val, msg = self._bytes_proc.parse(msg, **kwargs)
            try:
                ret_val = int(val.hex()), msg
            except ValueError as e:
                raise NotAbleToParseError(str(e), self.__class__, self._schemer)
            return ret_val
        else:
            return None, msg

    @check_input_to_build(int)
    @add_debug_log_msg
    def build(self, integer, **kwargs):
        int_in_str = str(integer)
        if len(int_in_str) % 2:
            int_in_str = "0" + int_in_str

        return  self._bytes_proc.build(bytes.fromhex(int_in_str), **kwargs)


class StrProc(Proc):
    __default_typeid__ = 'ascii'

    @classmethod
    @add_debug_log_msg
    def from_str(cls, str_val, schemer, **kwargs):

        if str_val == "ascii":
            spec = {'type': 'ascii'}
        elif str_val == "ebcdic":
            spec = {'type': 'ebcdic'}
        elif str_val == "binary":
            spec = {'type': 'binary'}
        else:
            raise NotAbleToCreateError(f'"type":"{str_val}" not supported', cls, schemer)

        return cls.from_dict(spec, schemer, **kwargs)

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')

    def __init__(self, bytes_proc, schemer):
        self._bytes_proc = bytes_proc

        self._schemer = schemer


class StrFromAsciiProc(StrProc):
    __typeid__ = 'ascii'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        if not "alignment" in kwargs:
            kwargs["alignment"] = "left"
        if not "pad_char" in kwargs:
            kwargs["pad_char"] = " "

        kwargs["pad_char"] = kwargs["pad_char"].encode(encoding="latin-1")

        bytes_proc = BytesProc.from_val(spec.get('value'), schemer, **kwargs)

        return cls(bytes_proc, schemer)

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        val, msg = self._bytes_proc.parse(msg, **kwargs)
        try:
            ret_val = val.decode(encoding="latin-1"), msg
        except UnicodeDecodeError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

        return ret_val

    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, str_val, **kwargs):
        try:
            ret_val = self._bytes_proc.build(str_val.encode(encoding="latin-1"),
                                             **kwargs)
        except UnicodeEncodeError as e:
            raise NotAbleToBuildError(str(e), self.__class__, self._schemer)
        return ret_val


class StrFromEbcdicProc(StrProc):
    __typeid__ = 'ebcdic'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        if not "alignment" in kwargs:
            kwargs["alignment"] = "left"
        if not "pad_char" in kwargs:
            kwargs["pad_char"] = " "

        kwargs["pad_char"] = encode(kwargs["pad_char"], "cp500")

        bytes_proc = BytesProc.from_val(spec.get('value'), schemer, **kwargs)
        return  cls(bytes_proc, schemer)

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
            val, msg = self._bytes_proc.parse(msg, **kwargs)
            try:
                ret_val = decode(val, "cp500"), msg
            except UnicodeDecodeError as e:
                raise NotAbleToParseError(str(e), self.__class__, self._schemer)
            return ret_val

    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, str_val, **kwargs):
        try:
            ret_val = self._bytes_proc.build(encode(str_val, "cp500"), **kwargs)
        except UnicodeEncodeError as e:
            raise NotAbleToBuildError(str(e), self.__class__, self._schemer)
        return ret_val


class StrFromBinProc(StrProc):
    __typeid__ = 'binary'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        if not "alignment" in kwargs:
            kwargs["alignment"] = "right"

        kwargs["pad_char"] = bytes.fromhex("00")

        bytes_proc = BytesProc.from_val(spec.get('value'), schemer, **kwargs)
        return  cls(bytes_proc, schemer)

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        val, msg = self._bytes_proc.parse(msg, **kwargs)
        return val.hex().upper(), msg

    @check_input_to_build(str)
    @add_debug_log_msg
    def build(self, str_val, **kwargs):

        if len(str_val) % 2:
            # Todo: Not works allways correctly (check also build methodn in IndicatorLenProc) :
            #   - for VISA this is fine as in case of nibble left padding by 0 is expected
            #   - for HPDH does not work as expected as right padding with F is expected
            str_val = "0" + str_val

        try:
            ret_val = self._bytes_proc.build(bytes.fromhex(str_val), **kwargs)
        except ValueError as e:
            raise NotAbleToBuildError(str(e), self.__class__, self._schemer)
        return ret_val


class BytesProc(Proc):
    __default_typeid__ = 'raw_data'

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')


class BytesFromRawDataProc(BytesProc):
    __typeid__ = 'raw_data'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        len_proc = LenProc.from_val(kwargs.pop('len', None), schemer, **kwargs)

        return cls(len_proc, schemer)

    def __init__(self, len_proc, schemer):
        self._len_proc = len_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        return self._len_proc.parse(msg, **kwargs)

    @check_input_to_build(bytes)
    @add_debug_log_msg
    def build(self, bytes_buff, **kwargs):
        return self._len_proc.build(bytes_buff, **kwargs)



class BitmapProc(Proc):
    __default_typeid__ = 'string'

    @classmethod
    @abstractmethod
    def create(cls, spec, schemer, **kwargs):
        raise NotImplementedError('abstract method')


class BitmapFromStrProc(BitmapProc):
    __typeid__ = 'string'

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        kwargs["alignment"] = "left"
        kwargs["pad_char"] = "0"

        str_proc = StrProc.from_val(spec.get('value'), schemer, **kwargs)
        return cls(str_proc, schemer)

    def __init__(self, str_proc, schemer):
        self._str_proc = str_proc

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        val, msg = self._str_proc.parse(msg, **kwargs)
        try:
            bit_string = BitArray(hex=val).bin
        except CreationError as e:
            raise NotAbleToParseError(str(e), self.__class__, self._schemer)

        #
        #   Convert bit string to array of bolleans
        #
        return [True if i == "1" else False for i in bit_string], msg

    @check_input_to_build(list)
    @add_debug_log_msg
    def build(self, bitmap, **kwargs):
        bitmap = bitmap + [False] * (len(bitmap) % 8)

        bitmap_as_bit_array = BitArray(bin="".join(["1" if i is True else "0" for i in bitmap]))
        return self._str_proc.build(bitmap_as_bit_array.hex.upper(), **kwargs)



class LenTagVal(Base):
    @classmethod
    def from_dict(cls, dict_val, schemer, **kwargs):
        ltv = cls.create(dict_val, schemer, **kwargs)
        return ltv

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):
        schemer._loc_key.append("tag_id")
        tag_id_val_len_proc = LenProc.from_val(spec['tag_id_val_len'], schemer, **kwargs)
        tag_id_node_proc = NodeProc.from_val(spec['tag_id'], schemer, **kwargs)
        tag_val_node_proc = NodeProc.from_val(spec['tag_val'], schemer, **kwargs)
        schemer._loc_key.pop()

        tags_dict = {}
        for tag_id, node_proc_val in spec.get('tags', {}).items():
            schemer._loc_key.append(tag_id)
            tags_dict[tag_id] = NodeProc.from_val(node_proc_val, schemer, **kwargs)
            schemer._loc_key.pop()

        id_mapping_dict = spec.get('id_mapping', {})

        ltv = cls(tag_id_val_len_proc, tag_id_node_proc, tag_val_node_proc, tags_dict, id_mapping_dict, schemer)
        return ltv

    def __init__(self, tag_id_val_len_proc,  tag_id_node_proc, tag_val_node_proc, tags_dict, id_mapping_dict, schemer):
        self._tag_id_val_len_proc = tag_id_val_len_proc
        self._tag_id_node_proc = tag_id_node_proc
        self._tag_val_node_proc = tag_val_node_proc
        self._tags_dict = tags_dict
        self._id_mapping_dict = id_mapping_dict

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        ltv_dict = {}

        while msg:

            tag_id_val_buff, msg = self._tag_id_val_len_proc.parse(msg, **kwargs)
            tag_id,  tag_val_buff = self._tag_id_node_proc.parse(tag_id_val_buff, **kwargs)
            self._schemer._loc_key.append(tag_id)
            if tag_id in self._tags_dict:
                tag_val, _ = self._tags_dict[tag_id].parse(tag_val_buff, **kwargs)
            else:
                tag_val, _ = self._tag_val_node_proc.parse(tag_val_buff, **kwargs)
            self._schemer._loc_key.pop()
            if tag_id in self._id_mapping_dict:
                tag_id = self._id_mapping_dict[tag_id]
            ltv_dict[tag_id] = tag_val

        return ltv_dict, msg

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, tlv_dict, **kwargs):
        ltv_buff = b""
        id_mapping_dict = {value:key for key, value in self._id_mapping_dict.items()}
        for tag_id, tag_val in tlv_dict.items():
            if tag_id in id_mapping_dict:
                tag_id = id_mapping_dict[tag_id]

            self._schemer._loc_key.append(tag_id)

            tag_id_val_buff = self._tag_id_node_proc.build(tag_id, **kwargs)
            if tag_id in self._tags_dict:
                tag_id_val_buff = tag_id_val_buff + self._tags_dict[tag_id].build(tag_val, **kwargs)
            else:
                tag_id_val_buff = tag_id_val_buff + self._tag_val_node_proc.build(tag_val, **kwargs)

            ltv_buff = ltv_buff + self._tag_id_val_len_proc.build(tag_id_val_buff, **kwargs)

            self._schemer._loc_key.pop()
        return ltv_buff



class TagLenVal(Base):
    @classmethod
    def from_dict(cls, dict_val, schemer, **kwargs):
        tlv = cls.create(dict_val, schemer, **kwargs)
        return tlv

    @classmethod
    @add_debug_log_msg
    def create(cls, spec, schemer, **kwargs):

        schemer._loc_key.append("tag_id")
        tag_id_node_proc = NodeProc.from_val(spec['tag_id'], schemer, **kwargs)
        tag_val_node_proc = NodeProc.from_val(spec['tag_val'], schemer, **kwargs)
        schemer._loc_key.pop()

        tags_dict = {}
        for tag_id, node_proc_val in spec.get('tags', {}).items():
            schemer._loc_key.append(tag_id)
            tags_dict[tag_id] = NodeProc.from_val(node_proc_val, schemer, **kwargs)
            schemer._loc_key.pop()

        id_mapping_dict = spec.get('id_mapping', {})

        tlv = cls(tag_id_node_proc, tag_val_node_proc, tags_dict, id_mapping_dict, schemer)
        return tlv

    def __init__(self, tag_id_node_proc, tag_val_node_proc, tags_dict, id_mapping_dict, schemer):
        self._tag_id_node_proc = tag_id_node_proc
        self._tag_val_node_proc = tag_val_node_proc
        self._tags_dict = tags_dict
        self._id_mapping_dict = id_mapping_dict

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        tlv_dict = {}

        while msg:
            tag_id,  msg = self._tag_id_node_proc.parse(msg, **kwargs)
            self._schemer._loc_key.append(tag_id)
            if tag_id in self._tags_dict:
                tag_val, msg = self._tags_dict[tag_id].parse(msg, **kwargs)
            else:
                tag_val, msg = self._tag_val_node_proc.parse(msg, **kwargs)
            self._schemer._loc_key.pop()
            if tag_id in self._id_mapping_dict:
                tag_id = self._id_mapping_dict[tag_id]
            tlv_dict[tag_id] = tag_val

        return tlv_dict, msg

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, tlv_dict, **kwargs):
        tlv_buff = b""
        id_mapping_dict = {value:key for key, value in self._id_mapping_dict.items()}
        for tag_id, tag_val in tlv_dict.items():
            if tag_id in id_mapping_dict:
                tag_id = id_mapping_dict[tag_id]

            self._schemer._loc_key.append(tag_id)
            tlv_buff = tlv_buff + self._tag_id_node_proc.build(tag_id, **kwargs)
            if tag_id in self._tags_dict:
                tlv_buff = tlv_buff + self._tags_dict[tag_id].build(tag_val, **kwargs)
            else:
                tlv_buff = tlv_buff + self._tag_val_node_proc.build(tag_val, **kwargs)
            self._schemer._loc_key.pop()
        return tlv_buff


class Fields(Base):
    @classmethod
    def from_dict(cls, dict_val, schemer, **kwargs):
        return cls.create(dict_val, schemer,  **kwargs)

    @classmethod
    @add_debug_log_msg
    def create(cls, fields_dict, schemer, **kwargs):
        children_dict = {}
        for fld_name, node_proc_val in fields_dict.items():
            schemer._loc_key.append(fld_name)
            children_dict[fld_name] = NodeProc.from_val(node_proc_val, schemer, **kwargs)
            schemer._loc_key.pop()

        return cls(children_dict, schemer)

    def __init__(self, children_dict, schemer):
        self._children_dict = children_dict

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, bitmap, **kwargs):
        parsed_flds_dict = {}

        for fld_present, fld_name, fld_processor in zip(bitmap, self._children_dict.keys(), self._children_dict.values()):

            if fld_present and msg:
                self._schemer._loc_key.append(fld_name)
                parsed_flds_dict[fld_name], msg = fld_processor.parse(msg, **kwargs)
                self._schemer._loc_key.pop()
            elif not msg:
                break

        return parsed_flds_dict, msg

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, flds_dict, **kwargs):

        bitmap = []
        flds_raw_val = b''
        for fld_name, fld_processor in self._children_dict.items():
            if fld_name in flds_dict:

                self._schemer._loc_key.append(fld_name)
                fld_raw_val = fld_processor.build(flds_dict[fld_name], **kwargs)
                self._schemer._loc_key.pop()
                flds_raw_val = flds_raw_val + fld_raw_val
                bitmap.append(True)
            else:
                bitmap.append(False)
        return flds_raw_val, bitmap


class Blocks(Base):
    __default_subtype__ = 'weaved'

    @classmethod
    def from_list(cls, list_val, schemer,  **kwargs):
        return cls.create(list_val, schemer, **kwargs)

    @classmethod
    @add_debug_log_msg
    def create(cls, blocks_list, schemer, **kwargs):

        subtype = kwargs.pop('subtype', getattr(cls, '__default_subtype__'))

        blocks_list_tmp = []
        for i, block_val in enumerate(blocks_list):
            blocks_list_tmp.append(Block.from_val(block_val, schemer, **kwargs))
        blocks_list = blocks_list_tmp

        bitmap_wrappers = []
        block_wrappers = []
        for block in blocks_list:
            bitmap_wrappers.append(block.parse_bitmap)
            block_wrappers.append(block.parse)

        wrappers = []
        if subtype == "weaved":
            for bitmap_wrapper, block_wrapper in zip(bitmap_wrappers, block_wrappers):
                wrappers = (wrappers[:-1] + [bitmap_wrapper] + wrappers[-1:] + [block_wrapper])
        else:
            wrappers = bitmap_wrappers + block_wrappers

        return cls(blocks_list, wrappers, subtype, schemer)

    def __init__(self, blocks_list, parse_wrappers_list, subtype, schemer):
        self._blocks_list = blocks_list
        self._parse_wrappers_list = parse_wrappers_list
        self._subtype = subtype

        self._schemer = schemer

    @add_debug_log_msg
    def parse(self, msg, **kwargs):
        bitmaps = []
        next_block_ind = True
        parsed_list = []
        for wrapper in self._parse_wrappers_list:

            parsed_list, next_block_ind, bitmaps, msg = wrapper(msg, next_block_ind, bitmaps, parsed_list, **kwargs)

        parsed_dict = {}
        for item in parsed_list:
            parsed_dict.update(item)

        return parsed_dict, msg

    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, blocks_dict, **kwargs):
        block_raw_msg_list = []
        block_bitmap_list = []

        for block in self._blocks_list:
            block_raw_msg, block_bitmap = block.build(blocks_dict, **kwargs)

            block_bitmap_list.append(block_bitmap)
            block_raw_msg_list.append(block_raw_msg)

        raw_msg_list = []

        for i, [block_raw_msg, block_bitmap] in enumerate(zip(block_raw_msg_list, block_bitmap_list)):
            #
            #  set next block ind to True if there is any next block with content
            #
            if any(block_raw_msg_list[i+1:]):
                next_block_ind = True
            else:
                next_block_ind = False


            #
            #   Add bitmap and fields if current or any next block contains content
            #   or
            #   it is a first block (MADA DE123)
            #
            #   todo: double check VISA DE062, DE063, DE126 what is happen if there is no SFs in these DEs: Len ind is present with 0 len or Len ind contain value 8 and bitmap is present with 0s
            #
            #
            if any(block_raw_msg_list[i:]) or i == 0:
                if self._subtype == "sequence":

                    list_middle_pos = int((len(raw_msg_list)/2))
                    raw_msg_list = (
                                    raw_msg_list[:list_middle_pos] +
                                    [self._blocks_list[i].build_bitmap(block_bitmap, next_block_ind, **kwargs)] +
                                    raw_msg_list[list_middle_pos:] +
                                    [block_raw_msg]
                                    )
                else:

                    raw_msg_list = (
                                    raw_msg_list[:-1] +
                                    [self._blocks_list[i].build_bitmap(block_bitmap, next_block_ind, **kwargs)] +
                                    raw_msg_list[-1:] +
                                    [block_raw_msg]
                                    )

        return b''.join(raw_msg_list)


class Block(Base):
    __default_next_block_ind_pos___ = None

    @classmethod
    def from_dict(cls, dict_val, schemer, **kwargs):
        return cls.create(dict_val, schemer, **kwargs)

    @classmethod
    @add_debug_log_msg
    def create(cls, block_spec, schemer, **kwargs):
        next_block_ind_pos = block_spec.get('next_block_ind_pos', getattr(cls, '__default_next_block_ind_pos___'))

        try:
            bitmap_proc = BitmapProc.from_val(block_spec['bitmap'], schemer)
        except KeyError:
            raise NotAbleToCreateError('"bitmap" is mandatory', cls, schemer)
        try:
            fields = Fields.from_val(block_spec['fields'], schemer)
        except KeyError:
            raise NotAbleToCreateError('"fields" is mandatory', cls, schemer)

        return cls(bitmap_proc, fields, next_block_ind_pos, schemer)

    def __init__(self, bitmap_proc, fields, next_block_ind_pos, schemer):
        self._bitmap_proc = bitmap_proc
        self._next_block_ind_pos = next_block_ind_pos
        self._fields = fields

        self._schemer = schemer

    @add_debug_log_msg
    def parse_bitmap(self, msg, next_block_ind, bitmaps, parsed, **kwargs):
        fields_count = len(self._fields._children_dict)

        if next_block_ind:

            bitmap, msg = self._bitmap_proc.parse(msg, **kwargs)

            bitmap_len = len(bitmap)

            #
            #   Pad the bitmap from left with False
            #

            if fields_count > bitmap_len:
                bitmap = [False] * (fields_count - bitmap_len) + bitmap
            #
            #   Add False for next block indicator if not present
            #
            bitmap_len = len(bitmap)
            if self._next_block_ind_pos and fields_count == bitmap_len:
                bitmap = [False] + bitmap

            #
            #   Parse the next block indicator
            #
            if self._next_block_ind_pos == 'msbit':
                next_block_ind, bitmap = bitmap[0], bitmap[1:]
            elif self._next_block_ind_pos == 'lsbit':
                next_block_ind, bitmap = bitmap[-1], bitmap[:-1]
            else:
                next_block_ind = False

            bitmaps.append(bitmap)

        else:
            next_block_ind = False
            bitmaps.append([False] * fields_count)

        return parsed, next_block_ind, bitmaps, msg

    @add_debug_log_msg
    def build_bitmap(self, bitmap, next_block_ind, **kwargs):

        if self._next_block_ind_pos == 'msbit':
            bitmap = [next_block_ind] + bitmap

        elif self._next_block_ind_pos == 'lsbit':
            bitmap = bitmap + [next_block_ind]

        return self._bitmap_proc.build(bitmap, **kwargs)

    @add_debug_log_msg
    def parse(self, msg, next_block_ind, bitmaps, parsed, **kwargs):
        bitmap = bitmaps.pop(0)

        fields, msg = self._fields.parse(msg, bitmap, **kwargs)
        parsed.append(fields)
        return parsed, next_block_ind, bitmaps, msg


    @check_input_to_build(dict)
    @add_debug_log_msg
    def build(self, blocks_dict, **kwargs):
        return self._fields.build(blocks_dict, **kwargs)


class Schemer:
    
    def __init__(self):
        self._schema_dict = {}
        self._logger = None
        self._logger_name = ""
        self._schemas_config = {}

        self._loc_key = []

    def load_schemas(self, schemas_file=None, needded_schemas_list=None):

        base_path = ""
        if not schemas_file:
            base_path = dirname(__file__)

            schemas_file = join(base_path, "schemas.json")
        try:
            with open(schemas_file) as f:
                self._schemas_config = load(f)
        except FileNotFoundError as e:
            raise NotAbleToProcessConfig(e, self.__class__, self)

        for schema, schema_config in self._schemas_config.items():
            if (not needded_schemas_list) or (needded_schemas_list and schema in needded_schemas_list):
                if isinstance(schema_config, str):
                    self._schema_dict[schema] = Schema(join(base_path, schema_config), self)
                elif isinstance(schema_config, dict):
                    self._schema_dict[schema] = {}
                    for msg_type, schema_file in schema_config["msg_types"].items():
                        self._schema_dict[schema][msg_type] = Schema(join(base_path,  schema_file), self)

    def init_logging(self, log_filename, log_level, log_format=None, logger_name="Schemer"):

        if LoggerMgr.add_logger(logger_name):
            self._logger_name = logger_name
            self._logger = LoggerMgr.get_logger(logger_name)
            
            self._logger.set_log_level(log_level)

            log_dir = dirname(log_filename)
            if not isdir(log_dir):
                makedirs(log_dir)

            if not log_format:
                self._logger.add_rotating_file_handler(log_filename)
            else:
                self._logger.add_rotating_file_handler(log_filename, log_format)
            return True
        else:
            return False

    def enable_logging(self):
        if self._logger:
            self._logger.enable()

    def disable_logging(self):
        if self._logger:
            self._logger.disable()

    def set_log_level(self, log_level):
        if self._logger:
            self._logger.set_log_level(log_level)

    def parse(self, input_msg, schema_name, msg_type=None):

        if isinstance(self._schema_dict[schema_name], Schema):

            schema = self._schema_dict[schema_name]
        else:
            if msg_type is None:
                schema = self._schema_dict[schema_name][next(iter(self._schema_dict[schema_name]))]
            else:
                schema = self._schema_dict[schema_name][msg_type]

        LoggerMgr.log(self._logger_name, INFO, f"parsing {schema_name} {msg_type} message: {input_msg}")
        ret_val = schema.parse(input_msg)
        LoggerMgr.log(self._logger_name, INFO, f"parsing for {schema_name} {msg_type} successful: {ret_val}")
        #
        #   Do additional parsing if there are parsing rules and msg_type is not passed
        #

        if msg_type is None and "parsing_rules" in self._schemas_config[schema_name]:
            for msg_type, conds in self._schemas_config[schema_name]['parsing_rules'].items():
                if JsonObjUtils.evaluate_conds(ret_val[0], conds):

                    schema = self._schema_dict[schema_name][msg_type]
                    LoggerMgr.log(self._logger_name, INFO, f"parsing {schema_name} {msg_type} message: {input_msg}")
                    ret_val = schema.parse(input_msg)
                    LoggerMgr.log(self._logger_name, INFO, f"parsing for {schema_name} {msg_type} successful: {ret_val}")
                    break

        return ret_val

    def build(self, json_obj, schema_name, msg_type=None):

        schema = None
        if isinstance(self._schema_dict[schema_name], Schema):
            schema = self._schema_dict[schema_name]
        else:
            if msg_type is None:
                if "building_rules" in self._schemas_config[schema_name]:
                    schema = self._schema_dict[schema_name][next(iter(self._schema_dict[schema_name]))]
                    for msg_type, conds in self._schemas_config[schema_name]['building_rules'].items():
                        if JsonObjUtils.evaluate_conds(json_obj, conds):
                            schema = self._schema_dict[schema_name][msg_type]
                            break
                else:
                    schema = self._schema_dict[schema_name][next(iter(self._schema_dict[schema_name]))]
            else:
                schema = self._schema_dict[schema_name][msg_type]

        LoggerMgr.log(self._logger_name, INFO, f"building {schema_name} {msg_type} message: {json_obj}")
        ret_val = schema.build(json_obj)
        LoggerMgr.log(self._logger_name, INFO, f"building for {schema_name} {msg_type} successful: {ret_val}")

        return ret_val

    def msg_type_supported(self, schema, msg_type):
        try:
            if msg_type in self._schema_dict[schema]:
                return True
            else:
                return False
        except KeyError:
            return False

    def get_supported_msg_types(self, schema):
        try:
            if isinstance(self._schema_dict[schema], dict):
                return list(self._schema_dict[schema].keys())
            else:
                return []
        except KeyError:
            return []

    def schema_supported(self, schema):
        return schema in self._schema_dict.keys()

    def get_supported_schemas(self):
        return list(self._schema_dict.keys())


class Schema:
    def __init__(self, schema_file, schemer):
        self._root_proc = None
        self._schemer = schemer
        try:
            LoggerMgr.log(self._schemer._logger_name, INFO, f"parsing: {schema_file}")
            with open(schema_file) as f:
                self._schemer._loc_key = []
                self._root_proc = NodeProc.from_val(load(f), self._schemer)

            LoggerMgr.log(self._schemer._logger_name, INFO, f"file: {schema_file} parsed successfully")
        except FileNotFoundError as e:
            raise NotAbleToCreateError(e, self.__class__, schemer)
        except JSONDecodeError as e:
            raise NotAbleToCreateError(e, self.__class__, schemer)

    def parse(self, input_msg):
        #
        #   Create a copy to ensure that input_msg is not changed during parsing
        #
        input_msg_copy = copy(input_msg)
        self._schemer._loc_key = []

        if self._root_proc:
            return self._root_proc.parse(input_msg_copy)
        else:
            LoggerMgr.log(self._schemer._logger_name,
                          ERROR,
                          f"parsing unsuccessful: schema is not initialized properly")
            return None

    def build(self, json_obj):
        self._schemer._loc_key = []

        if self._root_proc:
            return self._root_proc.build(json_obj)
        else:
            LoggerMgr.log(self._schemer._logger_name,
                          ERROR,
                          f"building unsuccessful: schema is not initialized properly")
            return None
