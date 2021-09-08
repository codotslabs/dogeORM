# 数据库工具

import threading
import time
import traceback
import warnings
from contextlib import contextmanager
from functools import wraps
from urllib.parse import urlparse, parse_qsl

import pymysql
from dbutils.pooled_db import PooledDB

from setting import dbUrl, Map

warnings.filterwarnings("ignore")


def __parse_result_to_dict(parsed):
	# 解析连接字符串
	path_parts = parsed.path[1:].split('?')
	query = parsed.query
	connect_kwargs = {'db': path_parts[0]}
	if parsed.username:
		connect_kwargs['user'] = parsed.username
	if parsed.password:
		connect_kwargs['password'] = parsed.password
	if parsed.hostname:
		connect_kwargs['host'] = parsed.hostname
	if parsed.port:
		connect_kwargs['port'] = parsed.port

	# MySql  参数
	if 'password' in connect_kwargs:
		connect_kwargs['passwd'] = connect_kwargs.pop('password')

	# 字符串解析
	qs_args = parse_qsl(query, keep_blank_values=True)
	for key, value in qs_args:
		if value.lower() == 'false':
			value = False
		elif value.lower() == 'true':
			value = True
		elif value.isdigit():
			value = int(value)
		elif '.' in value and all(p.isdigit() for p in value.split('.', 1)):
			try:
				value = float(value)
			except ValueError:
				pass
		elif value.lower() in ('null', 'none'):
			value = None
		connect_kwargs[key] = value
	if 'maxsize' in connect_kwargs:
		connect_kwargs['maxconnections'] = connect_kwargs.pop('maxsize')
	return connect_kwargs


def __create_pool(url):
	# 创建连接池
	parsed = urlparse(url)
	connect_kwargs = __parse_result_to_dict(parsed)
	return PooledDB(pymysql, 1, **connect_kwargs)


# 数据库连接
global setting, _transaction_map, pool

if "transaction_map" not in globals():
	global _transaction_map
	_transaction_map = {}

if "pool" not in globals():
	global pool
	pool = __create_pool(dbUrl)


def __get_connection():
	# 获取数据库链接
	tid = threading.get_ident()
	if tid in _transaction_map:
		return _transaction_map.get(tid)
	else:
		return pool.connection()


def __close_connection(conn):
	# 归还数据库链接
	tid = threading.get_ident()
	if tid in _transaction_map:
		return
	else:
		conn.close()


@contextmanager
def dbp():
	# with  数据库方法块
	f = __get_connection()
	yield f
	__close_connection(f)


def execute_sql(sql, params=None):
	"""执行sql
		execute_sql("update wallet set money=money+? where uid=?",10,1)
	"""
	with dbp() as db:
		c = db.cursor()
		c.execute(sql, params)
		db.commit()
		c.close()


def execute_sql_list(sqls):
	"""批量执行sql语句"""
	with dbp() as db:
		c = db.cursor()
		for sql in sqls:
			c.execute(sql)
		db.commit()
		c.close()


def __get_obj_list_sql(obj_list, table, replace=True):
	# 获取对象插入sql以及对应参数
	if obj_list:
		obj = obj_list[0]
		keys = list(map(lambda x: f"`{x}`", obj.keys()))
		values = list(map(lambda x: "%s", obj.keys()))
		if replace:
			sql = f"""replace INTO `{table}` ({",".join(keys)}) VALUES ({",".join(values)})"""
		else:
			sql = f"""insert INTO `{table}` ({",".join(keys)}) VALUES ({",".join(values)})"""
		params = []
		for obj in obj_list:
			params.append(tuple(obj.values()))
		return sql, params
	else:
		return "", []


def __get_obj_update_sql(obj, table, key):
	# 获取对象插入sql以及对应参数
	key_sql = f"where {key}='{obj[key]}'"
	del obj[key]
	keys = list(map(lambda x: f"`{x}`=%s", obj.keys()))
	sql = f"""update  `{table}` set {",".join(keys)} """ + key_sql
	params = tuple(obj.values())
	return sql, params


def sql_to_dict(sql, params=None):
	""" 查询sql，输出dict 列表
		    db_list=sql_to_dict("select * from users")
	:return List[Map]
	"""
	with dbp() as db:
		c = db.cursor()
		c.execute(sql, params)
		db_cols = len(c.description)
		col_names = [c.description[i][0] for i in range(db_cols)]
		db_list = c.fetchall()
		return_list = []
		for row in db_list:
			d = Map()
			for i in range(db_cols):
				if isinstance(row[i], bytes) and len(row[i]) == 1:
					d[col_names[i]] = True if row[i] == b'\x01' else False
				else:
					d[col_names[i]] = row[i]
			return_list.append(d)
		c.close()
		return return_list


def start_transaction():
	# 开始事务
	conn = __get_connection()
	conn.autocommit = False
	tid = threading.get_ident()
	_transaction_map[tid] = conn
	return tid


def end_transaction(rollback=False):
	# 结束事务
	tid = threading.get_ident()
	conn = _transaction_map.pop(tid)
	try:
		if rollback:
			conn.rollback()
		else:
			conn.commit()
	finally:
		conn.close()


@contextmanager
def transaction_code():
	"""with 事务方法块
		with transaction_code :
			last_uid=insert({"name":"珂珂"} "users")
			execute_sql("update users set sex=1 where id=?",last_uid)
	"""
	f = start_transaction()
	try:
		yield f
		end_transaction()
	except Exception:
		traceback.print_exc()
		end_transaction(True)


# 事务
def transaction(target_function):
	"""事务注解
		@transaction
		def save_user(name:str,sex:int):
			last_uid=insert(Map(name=name,sex=sex),"users")
			execute_sql("update users set sex=1 where id=?",last_uid)
	"""

	@wraps(target_function)
	def wrapper(*args, **kwargs):
		start_transaction()
		ret = target_function(*args, **kwargs)
		end_transaction()
		return ret

	return wrapper


def insert(obj, table):
	"""插入对象,返回id(如果有的话)
		last_uid=insert(Map(name=name,sex=sex),"users")
		last_uid=insert({"name":"珂珂"} "users")
	:return Map
	"""
	(sql, params) = __get_obj_list_sql([obj], table)
	with dbp() as db:
		c = db.cursor()
		c.execute(sql, params[0])
		db.commit()
		lid = c.lastrowid
		c.close()
		return lid


def update(obj, table, key="id"):
	"""更新数据
		update({"id":1,"name":"珂珂2"},"users")
	"""
	(sql, params) = __get_obj_update_sql(obj, table, key)
	with dbp() as db:
		c = db.cursor()
		c.execute(sql, params)
		db.commit()
		c.close()


def inserts(obj_list, table):
	"""批量插入
		insert_list=[{"name":"珂珂1","sex":1},{"name":"珂珂2","sex":0}]
		inserts(insert_list,"users")
	:return List[Map]
	"""
	if obj_list:
		(sql, params) = __get_obj_list_sql(obj_list, table)
		with dbp() as db:
			c = db.cursor()
			c.executemany(sql, params)
			db.commit()
			c.close()


def get(table, id, idstr="id"):
	"""数据库单条查询，根据id获取数据
		db_user=get("users",1)
		if db_user is not None:
			print(db_user.name)
	:return Map
	"""
	if isinstance(id, str): id = f"'{id}'"
	db_data = sql_to_dict(f"select * from {table} where {idstr}=?", id)
	if db_data:
		return db_data[0]
	return None


def get_list(table, where=None):
	"""根据条件返回表中数据，where不传则返回整表锁油数据
	一定要处理where条件中的注入问题
		db_list=get_list("users","sex=1")
	:return List[Map]
	"""
	if not where: return sql_to_dict(f"select * from {table}")
	return sql_to_dict(f"select * from {table} where {where}")


def __update_setting():
	global setting
	s = sql_to_dict("select name,value from setting")
	for i in s:
		setting[i["name"]] = i["value"]


def __update_setting_thread():
	while True:
		__update_setting()
		time.sleep(5)


# 系统设置
if "setting" not in vars():
	setting = Map()
	__update_setting()
	threading.Thread(target=__update_setting_thread, daemon=True).start()


def get_table_desc(table):
	db_fields = sql_to_dict(f"show full fields  from `{table}`")
	return_list = []
	for v in db_fields:
		return_list.append(Map({"name": v.Field, "type": v.Type, "commnet": v.Comment}))
	return return_list
