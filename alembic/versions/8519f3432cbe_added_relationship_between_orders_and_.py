"""added relationship between orders and users

Revision ID: 8519f3432cbe
Revises: e5fdc9223d21
Create Date: 2024-10-30 01:05:01.989092

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8519f3432cbe'
down_revision: Union[str, None] = 'e5fdc9223d21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###
