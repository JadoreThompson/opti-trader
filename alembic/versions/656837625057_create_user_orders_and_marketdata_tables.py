"""create user, orders and marketdata tables

Revision ID: 656837625057
Revises: 
Create Date: 2024-11-18 22:36:18.246509

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '656837625057'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('market_data',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('ticker', sa.String(), nullable=False),
    sa.Column('date', sa.Integer(), nullable=False),
    sa.Column('price', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id', 'date')
    )
    op.create_table('users',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('password', sa.String(), nullable=False),
    sa.Column('balance', sa.Float(), nullable=True),
    sa.Column('api_key', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('orders',
    sa.Column('order_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('order_status', sa.Enum('FILLED', 'PARTIALLY_FILLED', 'NOT_FILLED', 'CLOSED', 'PARTIALLY_CLOSED', name='order_status'), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('ticker', sa.String(), nullable=False),
    sa.Column('order_type', sa.Enum('MARKET', 'LIMIT', 'CLOSE', 'TAKE_PROFIT_CHANGE', 'STOP_LOSS_CHANGE', 'ENTRY_PRICE_CHANGE', name='order_type'), nullable=False),
    sa.Column('quantity', sa.Float(), nullable=False),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('filled_price', sa.Float(), nullable=True),
    sa.Column('limit_price', sa.Float(), nullable=True),
    sa.Column('take_profit', sa.Float(), nullable=True),
    sa.Column('stop_loss', sa.Float(), nullable=True),
    sa.Column('close_price', sa.Float(), nullable=True),
    sa.CheckConstraint('limit_price > 0', name='limit_price_minimum_value'),
    sa.CheckConstraint('quantity > 0', name='quantity_minimum_value'),
    sa.CheckConstraint('stop_loss > 0', name='stop_loss_minimum_value'),
    sa.CheckConstraint('take_profit > 0', name='take_profit_minimum_value'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('order_id'),
    sa.UniqueConstraint('order_id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('orders')
    op.drop_table('users')
    op.drop_table('market_data')
    # ### end Alembic commands ###