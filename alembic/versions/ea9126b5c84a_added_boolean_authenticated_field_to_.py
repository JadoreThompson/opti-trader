"""Added boolean authenticated field to Users Model

Revision ID: ea9126b5c84a
Revises: f80b4c0f3788
Create Date: 2024-12-18 16:11:06.337798

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea9126b5c84a'
down_revision: Union[str, None] = 'f80b4c0f3788'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('authenticated', sa.Boolean(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'authenticated')
    # ### end Alembic commands ###