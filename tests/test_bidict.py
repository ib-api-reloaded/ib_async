"""Test wrapper.BiDict."""

from ib_async.wrapper import BiDict


class TestBiDict:
    def test_add_and_get(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")
        bidict.add(2, "obj_b", "Value B")

        assert bidict.get_by_request_id(1) == "Value A"
        assert bidict.get_by_object_id("obj_b") == "Value B"
        assert bidict.get_request_id("obj_a") == 1
        assert len(bidict) == 2

    def test_add_overwrite_request_id(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")
        bidict.add(1, "obj_c", "Value C")  # Overwrite request_id 1

        assert bidict.get_by_request_id(1) == "Value C"
        assert (
            bidict.get_by_object_id("obj_a") is None
        )  # Old object_id should be removed
        assert bidict.get_request_id("obj_c") == 1
        assert len(bidict) == 1

    def test_add_overwrite_object_id(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")
        bidict.add(2, "obj_a", "Value B")  # Overwrite object_id "obj_a"

        assert bidict.get_by_object_id("obj_a") == "Value B"
        assert bidict.get_by_request_id(1) is None  # Old request_id should be removed
        assert bidict.get_request_id("obj_a") == 2
        assert len(bidict) == 1

    def test_remove_by_request_id(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")
        bidict.remove_by_request_id(1)

        assert bidict.get_by_request_id(1) is None
        assert bidict.get_by_object_id("obj_a") is None
        assert bidict.get_request_id("obj_a") is None
        assert len(bidict) == 0

    def test_remove_by_object_id(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")
        bidict.remove_by_object_id("obj_a")

        assert bidict.get_by_request_id(1) is None
        assert bidict.get_by_object_id("obj_a") is None
        assert bidict.get_request_id("obj_a") is None
        assert len(bidict) == 0

    def test_contains(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")

        assert 1 in bidict
        assert "obj_a" in bidict
        assert 2 not in bidict
        assert "obj_b" not in bidict

    def test_track_objects_weakly(self):
        class MyObject:
            def __init__(self, name):
                self.name = name

            def __hash__(self):
                return hash(self.name)

            def __eq__(self, other):
                return isinstance(other, MyObject) and self.name == other.name

        bidict = BiDict[str, MyObject](track_objects_weakly=True)

        obj_a = MyObject("A")
        obj_b = MyObject("B")

        bidict.add(1, "id_a", obj_a)
        bidict.add(2, "id_b", obj_b)

        assert bidict.get_request_id_by_object(obj_a) == 1
        assert bidict.get_request_id_by_object(obj_b) == 2

        # Test weak reference: if obj_a is no longer referenced, it should be removed
        del obj_a
        # The weakref might not be cleared immediately, but eventually it should be
        # gc.collect is not reliable to assert in tests
        # so just do a simple smoke test
        assert bidict.get_request_id_by_object(obj_b) == 2

        # Test removal with weak references
        obj_c = MyObject("C")
        bidict.add(3, "id_c", obj_c)
        assert bidict.get_request_id_by_object(obj_c) == 3
        bidict.remove_by_request_id(3)
        assert bidict.get_request_id_by_object(obj_c) is None

        obj_d = MyObject("D")
        bidict.add(4, "id_d", obj_d)
        assert bidict.get_request_id_by_object(obj_d) == 4
        bidict.remove_by_object_id("id_d")
        assert bidict.get_request_id_by_object(obj_d) is None

    def test_values(self):
        bidict = BiDict[str, object]()
        bidict.add(1, "obj_a", "Value A")
        bidict.add(2, "obj_b", "Value B")
        # get all values
        values = bidict.values()
        assert len(values) == 2
        assert "Value A" in values
        assert "Value B" in values
        # get values after delete
        bidict.remove_by_request_id(1)
        values = bidict.values()
        assert len(values) == 1
        assert "Value B" in values
        assert "Value A" not in values

    def test_update_request_id(self):
        bidict = BiDict[str, object]()
        obj_value = "My Test Object"
        object_id = "temp_key"
        initial_request_id = 100 # Represents an orderId
        final_request_id = 5000 # Represents a permId

        # Add the object with initial (dummy) request_id
        bidict.add(initial_request_id, object_id, obj_value)

        # Verify initial state
        assert bidict.get_by_request_id(initial_request_id) is obj_value
        assert bidict.get_by_object_id(object_id) is obj_value
        assert bidict.get_request_id(object_id) == initial_request_id
        assert len(bidict) == 1

        # Perform the update
        bidict.update_request_id(object_id, final_request_id)

        # Verify updated state
        assert bidict.get_by_request_id(initial_request_id) is None # Old request_id should no longer work
        assert bidict.get_by_request_id(final_request_id) is obj_value # New request_id should work
        assert bidict.get_by_object_id(object_id) is obj_value # object_id should still work
        assert bidict.get_request_id(object_id) == final_request_id # object_id maps to new request_id
        assert len(bidict) == 1 # Size should remain the same

        # Verify object identity (it's the same object, just re-indexed)
        retrieved_obj_by_new_req_id = bidict.get_by_request_id(final_request_id)
        retrieved_obj_by_obj_id = bidict.get_by_object_id(object_id)
        assert retrieved_obj_by_new_req_id is obj_value
        assert retrieved_obj_by_obj_id is obj_value
        assert retrieved_obj_by_new_req_id is retrieved_obj_by_obj_id
