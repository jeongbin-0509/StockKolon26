"""로컬 SQLite / 배포 PostgreSQL 저장소. 서비스의 내부 SQL만 처리한다."""

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import sqlite3

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


class DatabaseError(Exception):
    """연결 문자열·자격 증명을 노출하지 않는 저장소 오류."""


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def postgres_statement(statement):
    # 이 프로젝트의 정적 SQL에는 문자열 리터럴 내부의 ?가 없다. 값은 항상 별도 바인딩한다.
    statement = statement.replace('?', '%s')
    if statement.lstrip().upper().startswith('CREATE TABLE'):
        statement = statement.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY')
        statement = re.sub(r'\bINTEGER\b', 'BIGINT', statement)
        statement = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', statement)
    return statement


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self):
        return self.cursor.rowcount

    def fetchone(self):
        value = self.cursor.fetchone()
        return Row(value) if value is not None else None

    def fetchall(self):
        return [Row(value) for value in self.cursor.fetchall()]

    def __iter__(self):
        return (Row(value) for value in self.cursor)


class PostgresConnection:
    def __init__(self, connection):
        self.raw = connection

    def execute(self, statement, parameters=()):
        return Cursor(self.raw.execute(postgres_statement(statement), parameters))

    def executemany(self, statement, parameters):
        cursor = self.raw.cursor()
        cursor.executemany(postgres_statement(statement), parameters)
        return Cursor(cursor)


class Database:
    def __init__(self, location, schema='stockolon_private'):
        self.location = str(location)
        self.postgres = self.location.startswith(('postgres://', 'postgresql://'))
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema):
            raise ValueError('유효하지 않은 DB 스키마 이름입니다.')
        self.schema = schema
        self.lock_id = int.from_bytes(hashlib.sha256(schema.encode()).digest()[:8], 'big', signed=True)

    def _connect_postgres(self):
        try:
            options = conninfo_to_dict(self.location)
            options.setdefault('sslmode', 'require')
            options['connect_timeout'] = 10
            return psycopg.connect(**options, prepare_threshold=None, row_factory=dict_row)
        except (psycopg.Error, ValueError):
            raise DatabaseError('PostgreSQL 접속을 확인하세요. DATABASE_URL과 네트워크 설정이 필요합니다.') from None

    def initialize(self):
        if not self.postgres:
            return
        db = self._connect_postgres()
        try:
            with db.transaction():
                db.execute("SET LOCAL lock_timeout = '10s'")
                db.execute('SELECT pg_advisory_xact_lock(%s)', (self.lock_id,))
                db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
                db.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM PUBLIC').format(sql.Identifier(self.schema)))
                # Supabase의 브라우저 역할에는 관리자/세션/주가 내부 테이블을 노출하지 않는다.
                for role in ('anon', 'authenticated'):
                    if db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (role,)).fetchone():
                        db.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM {}').format(
                            sql.Identifier(self.schema), sql.Identifier(role)))
        except psycopg.Error:
            raise DatabaseError('PostgreSQL 전용 스키마를 준비하지 못했습니다.') from None
        finally:
            db.close()

    @contextmanager
    def connection(self, write=False):
        if not self.postgres:
            Path(self.location).parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.location, timeout=30)
            db.row_factory = sqlite3.Row
            try:
                if write:
                    db.execute('BEGIN IMMEDIATE')
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()
            return
        db = self._connect_postgres()
        try:
            with db.transaction():
                db.execute("SET LOCAL lock_timeout = '10s'")
                db.execute("SET LOCAL statement_timeout = '25s'")
                if write:
                    # 트랜잭션 풀러에서도 동일 스키마의 모든 쓰기를 직렬화한다.
                    db.execute('SELECT pg_advisory_xact_lock(%s)', (self.lock_id,))
                db.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(self.schema)))
                yield PostgresConnection(db)
        except psycopg.Error:
            raise DatabaseError('PostgreSQL 요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.') from None
        finally:
            db.close()
