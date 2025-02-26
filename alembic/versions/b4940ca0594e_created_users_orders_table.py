"""created users, orders table

Revision ID: b4940ca0594e
Revises: 
Create Date: 2025-02-26 18:18:29.239449

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4940ca0594e'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('users',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('avatar', sa.String(), nullable=False),
    sa.Column('balance', sa.Float(), server_default=sa.text('10000'), nullable=False),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('avatar'),
    sa.UniqueConstraint('email')
    )
    op.create_table('orders',
    sa.Column('trade_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('side', sa.String(), nullable=False),
    sa.Column('market_type', sa.String(), nullable=False),
    sa.Column('order_type', sa.String(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('limit_price', sa.Float(), nullable=True),
    sa.Column('stop_loss', sa.Float(), nullable=True),
    sa.Column('take_profit', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('trade_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('orders')
    op.drop_table('users')
    # ### end Alembic commands ###
