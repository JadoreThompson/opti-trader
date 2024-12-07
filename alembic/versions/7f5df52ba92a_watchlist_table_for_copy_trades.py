"""watchlist table for copy trades

Revision ID: 7f5df52ba92a
Revises: 8fd93e2adf68
Create Date: 2024-12-06 21:38:45.424510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f5df52ba92a'
down_revision: Union[str, None] = '8fd93e2adf68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('watchlist_user',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('master', sa.UUID(), nullable=False),
    sa.Column('watcher', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['master'], ['users.user_id'], ),
    sa.ForeignKeyConstraint(['watcher'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('watchlist_user')
    # ### end Alembic commands ###