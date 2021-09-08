from __future__ import unicode_literals
import hashlib, uuid
import json
import os
from datetime import date, datetime
from decimal import Decimal
from json import JSONEncoder

dbUrl = os.getenv("DB_URL", "mysql://user:pwd@dbhost:3306/database?charset=utf8mb4&maxsize=50")


class Map(dict):
	"""高级字典扩展类  通过点直接获取字典的值
	m = Map({'first_name': 'Eduardo'}, last_name='Pool', age=24, sports=['Soccer'])
	m=Map(first_name="Eduardo")
	m.first_name
	"""

	def __init__(self, *args, **kwargs):
		super(Map, self).__init__(*args, **kwargs)
		for arg in args:
			if isinstance(arg, dict):
				for k, v in arg.items():
					self[k] = v

		if kwargs:
			for k, v in kwargs.items():
				self[k] = v

	def __getattr__(self, attr):
		return self.get(attr)

	def __setattr__(self, key, value):
		self.__setitem__(key, value)

	def __getstate__(self):
		return self.__dict__

	def __setstate__(self, d):
		self.__dict__.update(d)

	def __setitem__(self, key, value):
		super(Map, self).__setitem__(key, value)
		self.__dict__.update({key: value})

	def __delattr__(self, item):
		self.__delitem__(item)

	def __delitem__(self, key):
		super(Map, self).__delitem__(key)
		del self.__dict__[key]

	def copy(self):
		n = Map(self.__dict__.copy())
		return n


def group_list(source_list, size):
	# 对列表按长度分组
	lc = source_list.copy()
	return_list = []
	if len(source_list) > size:
		while len(lc) >= size:
			return_list.append(lc[:size])
			lc = lc[size:]
		if len(lc) > 0: return_list.append(lc)
		return return_list
	else:
		return [source_list]


class MyEncoder(JSONEncoder):
	# 自定义json格式化标准
	def default(self, obj):
		if isinstance(obj, datetime):
			return obj.strftime('%Y-%m-%d %H:%M:%S')
		elif isinstance(obj, date):
			return obj.strftime('%Y-%m-%d')
		elif isinstance(obj, Decimal):
			return format(obj, 'f')
		else:
			return super(MyEncoder, self).default(obj)


# class MyDecoder(JSONDecoder):
def set_object_hook(obj):
	# 将json中的map替换为增强map
	if isinstance(obj, dict):
		return Map(obj)
	return obj


def loads(str):
	# json解析为python对象
	return json.loads(str, object_hook=set_object_hook, strict=False)


def dumps(obj):
	# python对象转为json字符串
	return json.dumps(obj, cls=MyEncoder, ensure_ascii=False)


def md5(content):
	# 获取字符串的md5
	return hashlib.md5(content.encode(encoding='UTF-8')).hexdigest()


def uuid_str():
	# 获取uuid
	return str(uuid.uuid4()).replace("-", "")
