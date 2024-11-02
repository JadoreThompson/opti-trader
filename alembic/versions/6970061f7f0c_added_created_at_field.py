"""added created at field

Revision ID: 6970061f7f0c
Revises: 7bd095b9beb1
Create Date: 2024-10-31 23:11:06.152598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6970061f7f0c'
down_revision: Union[str, None] = '7bd095b9beb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('orders', sa.Column('created_at', sa.DateTime(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('orders', 'created_at')
    # ### end Alembic commands ###
