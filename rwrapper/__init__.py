"""
@fileoverview rWrapper
@author David Parlevliet
@version 20130730
@preserve Copyright 2013 David Parlevliet.
"""
import rethinkdb as r
import json
import jsonpickle


class rwrapper(object):
    id = None

    _limit = 0
    _order_by = None
    _meta = None
    _changed = False
    _pickle = False
    _connection = None
    _upsert = False
    _non_atomic = True
    _ignore_fields = []

    class DoesNotExist(Exception):
        pass

    def __pickle__(self):
        self._pickle = True
        pickle = jsonpickle.encode(self)
        self._pickle = False
        return pickle

    def __init__(self, **kwargs):
        self._meta = {}
        for key in dir(self):
            try:
                if key.startswith('_') and not key == '_connection':
                    continue
                value = getattr(self, key)
                if not value.__rfield__:
                    continue
                self._meta[key] = value
                self._meta[key].name = key
                default = None
                if not value.default == '_rwrapper_default':
                    default = value.default
                setattr(self, key, default)
            except:
                continue
        for key in kwargs:
            try:
                setattr(self, key, self._meta[key].to_python(self._meta[key].validate(kwargs[key])))
            except:
                setattr(self, key, kwargs[key])

    def __json__(self):
        d = {}
        for key in dir(self):
            try:
                if not key is None and not key.startswith('_') and \
                        not hasattr(getattr(self, key), '__call__'):
                    d[key] = getattr(self, key)
            except:
                continue
        return d

    def __setattr__(self, name, value):
        try:
            if not name.startswith('_') and not value == getattr(self, name):
                self._changed = True
        except:
            pass
        return object.__setattr__(self, name, value)

    def __getattribute__(self, name):
        if name == '__dict__':
            if not self._pickle:
                return self.__json__()
        return object.__getattribute__(self, name)

    def evaluate_insert(self, result):
        if 'errors' in result and result['errors'] > 1:
            raise IOError(json.dumps(result))
        elif result['inserted'] == 1.0:
            self.id = result['generated_keys'][0]
        return self.id

    def evaluate_update(self, result):
        if 'updated' in result and result['updated'] == 0:
            raise ValueError(json.dumps(result))
        if 'replaced' in result and result['replaced'] == 0:
            raise ValueError(json.dumps(result))
        if 'errors' in result and result['errors'] > 0:
            raise IOError(json.dumps(result))
        return result

    def rq(self, filter=False):
        if not filter:
            filter = self._filter()
        rq = r.table(self._db_table)
        if len(filter) > 0 or hasattr(filter,'__call__'):
            rq = rq.filter(filter)
        if not self._order_by == None:
            rq = rq.order_by(*tuple([order if not order[:1] == '-' else \
                                         r.desc(order[1:]) for order in list(self._order_by)]))
        if not self._limit == 0:
            rq = rq.limit(int(self._limit))
        return rq

    def _filter(self):
        filter = {}
        for key, value in self.__dict__.iteritems():
            if key in self._meta and self._meta[key].default == value:
                continue
            if not value == None:
                filter[key] = value
        return filter

    def filter(self, filter_func, o=None):
        if hasattr(filter_func,'__call__'):
            return [row if o is None else o(**row) for row in self.rq(filter_func).run(self._connection)]
        else:
            raise ValueError('filter func must be callable')

    def all(self, o=None):
        return [row if o is None else o(**row) for row in self.rq().run(self._connection)]

    def get(self, o=None, exception=False):
        try:
            result = list(self.rq().limit(1).run(self._connection))[0]
            if o == dict:
                result = dict(result)
            else:
                result = result if o is None else o(**result)
                if o:
                    result.changed(False)
            return result
        except:
            if not exception:
                return None
            raise ValueError('Row not found in table.')

    def save(self):
        # Try and be lazy about saving. Only save if our values have actually
        # changed
        if not self._changed:
            return False

        # Validate any defined fields and set any defaults
        doc = self.__dict__
        if isinstance(self._meta, dict) and len(self._meta) > 0:
            for key in self._meta.keys():
                if key not in self._ignore_fields:
                    setattr(self, key, self._meta[key].validate(doc[key]))

        #Update doc
        doc = self.__dict__
        del doc['id']
        #Convert all value in doc to rethink before save
        for key in doc.keys():
            doc[key] = self._meta[key].to_rethink(doc[key])

        # id being none means we should insert
        if self.id is None:
            if 'id' in doc:
                del doc['id']
            self.changed(False)
            return self.evaluate_insert(r.table(self._db_table).insert(
                doc,
                upsert=self._upsert
            ).run(self._connection))

        # id found; update
        self.changed(False)
        return self.evaluate_update(r.table(self._db_table).filter({'id': self.id}).update(
            doc,
            non_atomic=self._non_atomic
        ).run(self._connection))

    def changed(self, value):
        if isinstance(value, bool):
            self._changed = False
        return self

    def order_by(self, *args):
        self._order_by = args
        return self

    def limit(self, amount):
        self._limit = amount
        return self

    def count(self, filter=False):
        return self.rq(filter).count().run(self._connection)

    def delete(self, filter=False):
        return self.rq(filter).delete().run(self._connection)

    def skip(self):
        raise NotImplemented

    def limit(self):
        raise NotImplemented
