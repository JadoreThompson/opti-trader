# import pytest
# from engine.balance_manager import BalanceManager


# @pytest.fixture
# def manager():
#     """Returns a BalanceManager instance."""
#     return BalanceManager()


# def test_append_new_user(manager):
#     """Test that a new user is added with a balance of 0."""
#     manager.append("user1")
#     assert manager.get_balance("user1") == 0


# def test_remove_user(manager):
#     """Test that a user can be removed."""
#     manager.append("user1")
#     manager.remove("user1")
#     assert manager.get_balance("user1") == 0  # Default for non-existent user


# def test_get_balance_non_existent_user(manager):
#     """Test that getting the balance of a non-existent user returns 0."""
#     assert manager.get_balance("non_existent_user") == 0


# def test_increase_balance(manager):
#     """Test that the balance for a user can be increased."""
#     manager.append("user1")
#     manager.increase_balance("user1", 100)
#     assert manager.get_balance("user1") == 100
#     manager.increase_balance("user1", 50)
#     assert manager.get_balance("user1") == 150


# def test_decrease_balance(manager):
#     """Test that the balance for a user can be decreased."""
#     manager.append("user1")
#     manager.increase_balance("user1", 100)
#     manager.decrease_balance("user1", 30)
#     assert manager.get_balance("user1") == 70


# def test_balance_operations_on_non_existent_user(manager):
#     """Test that balance operations on a non-existent user work as expected."""
#     manager.increase_balance("user2", 50)
#     assert manager.get_balance("user2") == 50
#     manager.decrease_balance("user2", 20)
#     assert manager.get_balance("user2") == 30

