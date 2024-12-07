"""username on users table & new table for copy trades

Revision ID: c2c7a146f9dd
Revises: 06122fd66878
Create Date: 2024-12-06 20:48:01.972821

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2c7a146f9dd'
down_revision: Union[str, None] = '06122fd66878'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('orders_user_id_fkey', 'orders', type_='foreignkey')
    op.create_foreign_key(None, 'orders', 'users', ['user_id'], ['user_id'])
    op.add_column('users', sa.Column('username', sa.String(), nullable=True))
    op.create_unique_constraint(None, 'users', ['username'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'users', type_='unique')
    op.drop_column('users', 'username')
    op.drop_constraint(None, 'orders', type_='foreignkey')
    op.create_foreign_key('orders_user_id_fkey', 'orders', 'users', ['user_id'], ['user_id'], ondelete='CASCADE')
    # ### end Alembic commands ###
