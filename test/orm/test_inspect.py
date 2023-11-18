"""test the inspection registry system."""

import random
import textwrap

from sqlalchemy import Column
from sqlalchemy import exc
from sqlalchemy import ForeignKey
from sqlalchemy import inspect
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy import testing
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.associationproxy import AssociationProxyExtensionType
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.hybrid import HybridExtensionType
from sqlalchemy.orm import aliased
from sqlalchemy.orm import class_mapper
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Session
from sqlalchemy.orm import synonym
from sqlalchemy.orm.attributes import instance_state
from sqlalchemy.orm.attributes import NO_VALUE
from sqlalchemy.orm.base import InspectionAttr
from sqlalchemy.orm.interfaces import NotExtension
from sqlalchemy.orm.util import identity_key
from sqlalchemy.testing import assert_raises_message
from sqlalchemy.testing import eq_
from sqlalchemy.testing import is_
from sqlalchemy.testing.fixtures import fixture_session
from test.orm import _fixtures


class TestORMInspection(_fixtures.FixtureTest):
    @classmethod
    def setup_mappers(cls):
        cls._setup_stock_mapping()
        inspect(cls.classes.User).add_property("name_syn", synonym("name"))

    def test_class_mapper(self):
        User = self.classes.User

        assert inspect(User) is class_mapper(User)

    def test_column_collection_iterate(self):
        User = self.classes.User
        user_table = self.tables.users
        insp = inspect(User)
        eq_(list(insp.columns), [user_table.c.id, user_table.c.name])
        is_(insp.columns.id, user_table.c.id)

    def test_primary_key(self):
        User = self.classes.User
        user_table = self.tables.users
        insp = inspect(User)
        eq_(insp.primary_key, (user_table.c.id,))

    def test_local_table(self):
        User = self.classes.User
        user_table = self.tables.users
        insp = inspect(User)
        is_(insp.local_table, user_table)

    def test_persist_selectable(self):
        User = self.classes.User
        user_table = self.tables.users
        insp = inspect(User)
        is_(insp.persist_selectable, user_table)

    def test_mapper_selectable(self):
        User = self.classes.User
        user_table = self.tables.users
        insp = inspect(User)
        is_(insp.selectable, user_table)
        assert not insp.is_selectable
        assert not insp.is_aliased_class

    def test_mapper_selectable_fixed(self):
        class Foo:
            pass

        class Bar(Foo):
            pass

        user_table = self.tables.users
        addresses_table = self.tables.addresses
        self.mapper_registry.map_imperatively(
            Foo, user_table, with_polymorphic=(Bar,)
        )
        self.mapper_registry.map_imperatively(
            Bar,
            addresses_table,
            inherits=Foo,
            properties={"address_id": addresses_table.c.id},
        )
        i1 = inspect(Foo)
        i2 = inspect(Foo)
        assert i1.selectable is i2.selectable

    def test_aliased_class(self):
        Address = self.classes.Address
        ualias = aliased(Address)
        insp = inspect(ualias)
        is_(insp.mapper, inspect(Address))
        is_(insp.selectable, ualias._aliased_insp.selectable)
        assert not insp.is_selectable
        assert insp.is_aliased_class

    def test_not_mapped_class(self):
        class Foo:
            pass

        assert_raises_message(
            exc.NoInspectionAvailable,
            "No inspection system is available for object of type",
            inspect,
            Foo,
        )

    def test_not_mapped_instance(self):
        class Foo:
            pass

        assert_raises_message(
            exc.NoInspectionAvailable,
            "No inspection system is available for object of type",
            inspect,
            Foo(),
        )

    def test_property(self):
        User = self.classes.User
        insp = inspect(User)
        is_(insp.attrs.id, class_mapper(User).get_property("id"))

    def test_with_polymorphic(self):
        User = self.classes.User
        insp = inspect(User)
        eq_(insp.with_polymorphic_mappers, [])

    def test_col_property(self):
        User = self.classes.User
        user_table = self.tables.users
        insp = inspect(User)
        id_prop = insp.attrs.id

        eq_(id_prop.columns, [user_table.c.id])
        is_(id_prop.expression, user_table.c.id)

        assert not hasattr(id_prop, "mapper")

    def test_attr_keys(self):
        User = self.classes.User
        insp = inspect(User)
        eq_(
            list(insp.attrs.keys()),
            ["addresses", "orders", "id", "name", "name_syn"],
        )

    def test_col_filter(self):
        User = self.classes.User
        insp = inspect(User)
        eq_(
            list(insp.column_attrs),
            [insp.get_property("id"), insp.get_property("name")],
        )
        eq_(list(insp.column_attrs.keys()), ["id", "name"])
        is_(insp.column_attrs.id, User.id.property)

    def test_synonym_filter(self):
        User = self.classes.User
        syn = inspect(User).synonyms

        eq_(list(syn.keys()), ["name_syn"])
        is_(syn.name_syn, User.name_syn.original_property)
        eq_(dict(syn), {"name_syn": User.name_syn.original_property})

    def test_relationship_filter(self):
        User = self.classes.User
        rel = inspect(User).relationships

        eq_(rel.addresses, User.addresses.property)
        eq_(set(rel.keys()), {"orders", "addresses"})

    def test_insp_relationship_prop(self):
        User = self.classes.User
        Address = self.classes.Address
        prop = inspect(User.addresses)
        is_(prop, User.addresses)
        is_(prop.parent, class_mapper(User))
        is_(prop._parentmapper, class_mapper(User))
        is_(prop.mapper, class_mapper(Address))

    def test_insp_aliased_relationship_prop(self):
        User = self.classes.User
        Address = self.classes.Address
        ua = aliased(User)
        prop = inspect(ua.addresses)
        is_(prop, ua.addresses)

        is_(prop.property.parent.mapper, class_mapper(User))
        is_(prop.property.mapper, class_mapper(Address))
        is_(prop.parent.entity, ua)
        is_(prop.parent.class_, User)
        is_(prop._parentmapper, class_mapper(User))
        is_(prop.mapper, class_mapper(Address))

        is_(prop._parententity, inspect(ua))

    def test_insp_column_prop(self):
        User = self.classes.User
        prop = inspect(User.name)
        is_(prop, User.name)

        is_(prop.parent, class_mapper(User))
        assert not hasattr(prop, "mapper")

    def test_insp_aliased_column_prop(self):
        User = self.classes.User
        ua = aliased(User)
        prop = inspect(ua.name)
        is_(prop, ua.name)

        is_(prop.property.parent.mapper, class_mapper(User))
        assert not hasattr(prop.property, "mapper")
        is_(prop.parent.entity, ua)
        is_(prop.parent.class_, User)
        is_(prop._parentmapper, class_mapper(User))

        assert not hasattr(prop, "mapper")

        is_(prop._parententity, inspect(ua))

    def test_rel_accessors(self):
        User = self.classes.User
        Address = self.classes.Address
        prop = inspect(User.addresses)
        is_(prop.property.parent, class_mapper(User))
        is_(prop.property.mapper, class_mapper(Address))
        is_(prop.parent, class_mapper(User))
        is_(prop.mapper, class_mapper(Address))

        assert not hasattr(prop, "columns")
        assert hasattr(prop, "expression")

    def test_extension_types(self):
        class SomeClass(self.classes.User):
            some_assoc = association_proxy("addresses", "email_address")

            @hybrid_property
            def upper_name(self):
                raise NotImplementedError()

            @hybrid_method
            def conv(self, fn):
                raise NotImplementedError()

        class Address(self.classes.Address):
            pass

        class SomeSubClass(SomeClass):
            @hybrid_property
            def upper_name(self):
                raise NotImplementedError()

            @hybrid_property
            def foo(self):
                raise NotImplementedError()

        m = MetaData()
        t = Table("sometable", m, Column("id", Integer, primary_key=True))
        ta = Table(
            "address_t",
            m,
            Column("id", Integer, primary_key=True),
            Column("s_id", ForeignKey("sometable.id")),
        )
        self.mapper_registry.map_imperatively(
            SomeClass, t, properties={"addresses": relationship(Address)}
        )
        self.mapper_registry.map_imperatively(Address, ta)
        self.mapper_registry.map_imperatively(SomeSubClass, inherits=SomeClass)

        insp = inspect(SomeSubClass)
        eq_(
            {
                k: v.extension_type
                for k, v in list(insp.all_orm_descriptors.items())
            },
            {
                "id": NotExtension.NOT_EXTENSION,
                "name": NotExtension.NOT_EXTENSION,
                "name_syn": NotExtension.NOT_EXTENSION,
                "addresses": NotExtension.NOT_EXTENSION,
                "orders": NotExtension.NOT_EXTENSION,
                "upper_name": HybridExtensionType.HYBRID_PROPERTY,
                "foo": HybridExtensionType.HYBRID_PROPERTY,
                "conv": HybridExtensionType.HYBRID_METHOD,
                "some_assoc": AssociationProxyExtensionType.ASSOCIATION_PROXY,
            },
        )
        is_(
            insp.all_orm_descriptors.upper_name,
            SomeSubClass.__dict__["upper_name"],
        )
        is_(insp.all_orm_descriptors.some_assoc, SomeClass.some_assoc.parent)
        is_(
            inspect(SomeClass).all_orm_descriptors.upper_name,
            SomeClass.__dict__["upper_name"],
        )

    def test_instance_state(self):
        User = self.classes.User
        u1 = User()
        insp = inspect(u1)
        is_(insp, instance_state(u1))

    def test_instance_state_info(self):
        User = self.classes.User
        u1 = User()
        insp = inspect(u1)
        insp.info["some_key"] = "value"
        eq_(inspect(u1).info["some_key"], "value")

    def test_instance_state_attr(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)

        eq_(
            set(insp.attrs.keys()),
            {"id", "name", "name_syn", "addresses", "orders"},
        )
        eq_(insp.attrs.name.value, "ed")
        eq_(insp.attrs.name.loaded_value, "ed")

    def test_instance_state_attr_passive_value_scalar(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        # value was not set, NO_VALUE
        eq_(insp.attrs.id.loaded_value, NO_VALUE)
        # regular accessor sets it
        eq_(insp.attrs.id.value, None)
        # nope, still not set
        eq_(insp.attrs.id.loaded_value, NO_VALUE)

    def test_instance_state_attr_passive_value_collection(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        # value was not set, NO_VALUE
        eq_(insp.attrs.addresses.loaded_value, NO_VALUE)
        # regular accessor sets it
        eq_(insp.attrs.addresses.value, [])
        # stays as NO_VALUE, this is #4519
        eq_(insp.attrs.addresses.loaded_value, NO_VALUE)

    def test_instance_state_collection_attr_hist(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        hist = insp.attrs.addresses.history
        eq_(hist.unchanged, ())
        u1.addresses
        hist = insp.attrs.addresses.history
        # stays, this is #4519
        eq_(hist.unchanged, ())

    def test_instance_state_scalar_attr_hist(self):
        User = self.classes.User
        u1 = User(name="ed")
        sess = fixture_session()
        sess.add(u1)
        sess.commit()
        assert "name" not in u1.__dict__
        insp = inspect(u1)
        hist = insp.attrs.name.history
        eq_(hist.unchanged, ())
        assert "name" not in u1.__dict__

    def test_instance_state_collection_attr_load_hist(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        hist = insp.attrs.addresses.load_history()
        eq_(hist.unchanged, ())
        u1.addresses
        hist = insp.attrs.addresses.load_history()
        # stays, this is #4519
        eq_(hist.unchanged, ())

    def test_instance_state_scalar_attr_hist_load(self):
        User = self.classes.User
        u1 = User(name="ed")
        sess = fixture_session()
        sess.add(u1)
        sess.commit()
        assert "name" not in u1.__dict__
        insp = inspect(u1)
        hist = insp.attrs.name.load_history()
        eq_(hist.unchanged, ["ed"])
        assert "name" in u1.__dict__

    def test_attrs_props_prop_added_after_configure(self):
        class Thing(InspectionAttr):
            pass

        class AnonClass:
            __foo__ = "bar"
            __bat__ = Thing()

        from sqlalchemy.orm import column_property
        from sqlalchemy.ext.hybrid import hybrid_property

        m = self.mapper_registry.map_imperatively(AnonClass, self.tables.users)

        eq_(set(inspect(AnonClass).attrs.keys()), {"id", "name"})
        eq_(
            set(inspect(AnonClass).all_orm_descriptors.keys()),
            {"id", "name"},
        )

        m.add_property("q", column_property(self.tables.users.c.name))

        def desc(self):
            return self.name

        AnonClass.foob = hybrid_property(desc)

        eq_(set(inspect(AnonClass).attrs.keys()), {"id", "name", "q"})
        eq_(
            set(inspect(AnonClass).all_orm_descriptors.keys()),
            {"id", "name", "q", "foob"},
        )

    def _random_names(self):
        import random
        import keyword

        def _random_name():
            while True:
                name = "".join(
                    random.choice("abcdegfghijklmnopqrstuvwxyz")
                    for i in range(random.randint(5, 15))
                )
                if name not in keyword.kwlist:
                    return name

        return [_random_name() for i in range(random.randint(8, 15))]

    def _ordered_name_fixture(self, glbls, clsname, base, supercls):
        names = self._random_names()

        if base is supercls:
            pk_names = {
                random.choice(names) for i in range(random.randint(1, 3))
            }
            fk_name = random.choice(
                [name for name in names if name not in pk_names]
            )
        else:
            pk_names = []
            fk_name = None

        def _make_name(name):
            if name in pk_names:
                return "%s = Column(Integer, primary_key=True)" % name
            elif name == fk_name:
                return "%s = Column(ForeignKey('myotherclass.id'))" % name
            else:
                type_ = random.choice(["relationship", "column", "hybrid"])
                if type_ == "relationship":
                    return "%s = relationship('MyOtherClass')" % name
                elif type_ == "column":
                    return "%s = Column(Integer)" % name
                elif type_ == "hybrid":
                    return (
                        "@hybrid_property\ndef %s(self):\n    return None"
                        % name
                    )

        glbls["Base"] = base
        glbls["SuperCls"] = supercls

        if base is supercls:

            class MyOtherClass(base):
                __tablename__ = "myotherclass"
                id = Column(Integer, primary_key=True)

            glbls["MyOtherClass"] = MyOtherClass
        code = """

from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property

class %s(SuperCls):
    %s

%s
""" % (
            clsname,
            "__tablename__ = 'mytable'" if base is supercls else "",
            "\n".join(
                textwrap.indent(_make_name(name), "    ") for name in names
            ),
        )

        exec(code, glbls)
        return names, glbls[clsname]

    def test_all_orm_descriptors_pep520_noinh(self):
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        glbls = {}
        names, MyClass = self._ordered_name_fixture(
            glbls, "MyClass", Base, Base
        )

        eq_(MyClass.__mapper__.all_orm_descriptors.keys(), names)

    def test_all_orm_descriptors_pep520_onelevel_inh(self):
        from sqlalchemy.orm import declarative_base

        Base = declarative_base()

        glbls = {}

        base_names, MyClass = self._ordered_name_fixture(
            glbls, "MyClass", Base, Base
        )

        sub_names, SubClass = self._ordered_name_fixture(
            glbls, "SubClass", Base, MyClass
        )

        eq_(
            SubClass.__mapper__.all_orm_descriptors.keys(),
            sub_names + base_names,
        )

    def test_all_orm_descriptors_pep520_classical(self):
        class MyClass:
            pass

        names = self._random_names()

        m = MetaData()
        t = Table(
            "t",
            m,
            Column("id", Integer, primary_key=True),
            *[Column(name, Integer) for name in names],
        )

        m = self.mapper_registry.map_imperatively(MyClass, t)

        eq_(m.all_orm_descriptors.keys(), ["id"] + names)

    def test_instance_state_ident_transient(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        is_(insp.identity, None)

    def test_instance_state_ident_persistent(self):
        User = self.classes.User
        u1 = User(name="ed")
        s = Session(testing.db)
        s.add(u1)
        s.flush()
        insp = inspect(u1)
        eq_(insp.identity, (u1.id,))
        is_(s.get(User, insp.identity), u1)

    def test_is_instance(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        assert insp.is_instance

        insp = inspect(User)
        assert not insp.is_instance

        insp = inspect(aliased(User))
        assert not insp.is_instance

    def test_identity_key(self):
        User = self.classes.User
        u1 = User(name="ed")
        s = Session(testing.db)
        s.add(u1)
        s.flush()
        insp = inspect(u1)
        eq_(insp.identity_key, identity_key(User, (u1.id,)))

    def test_persistence_states(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)

        eq_(
            (insp.transient, insp.pending, insp.persistent, insp.detached),
            (True, False, False, False),
        )
        s = Session(testing.db)
        s.add(u1)

        eq_(
            (insp.transient, insp.pending, insp.persistent, insp.detached),
            (False, True, False, False),
        )

        s.flush()
        eq_(
            (insp.transient, insp.pending, insp.persistent, insp.detached),
            (False, False, True, False),
        )
        s.expunge(u1)
        eq_(
            (insp.transient, insp.pending, insp.persistent, insp.detached),
            (False, False, False, True),
        )

    def test_session_accessor(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)

        is_(insp.session, None)
        s = fixture_session()
        s.add(u1)
        is_(insp.session, s)

    def test_object_accessor(self):
        User = self.classes.User
        u1 = User(name="ed")
        insp = inspect(u1)
        is_(insp.object, u1)
