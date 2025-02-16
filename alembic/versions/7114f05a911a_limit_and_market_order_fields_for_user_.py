"""limit and market order fields for user watchlist

Revision ID: 7114f05a911a
Revises: 8c7422b53359
Create Date: 2024-12-06 23:22:09.251629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7114f05a911a'
down_revision: Union[str, None] = '8c7422b53359'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('watchlist_user', sa.Column('limit_orders', sa.Boolean(), nullable=False))
    op.add_column('watchlist_user', sa.Column('market_orders', sa.Boolean(), nullable=False))
    op.create_foreign_key(None, 'watchlist_user', 'users', ['watcher'], ['user_id'], ondelete='CASCADE')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'watchlist_user', type_='foreignkey')
    op.drop_column('watchlist_user', 'market_orders')
    op.drop_column('watchlist_user', 'limit_orders')
    # ### end Alembic commands ###
