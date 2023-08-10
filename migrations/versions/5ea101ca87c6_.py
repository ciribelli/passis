"""empty message

Revision ID: 5ea101ca87c6
Revises: fa8ccd27c209
Create Date: 2023-08-09 20:58:09.821184

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5ea101ca87c6'
down_revision = 'fa8ccd27c209'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('checkins', schema=None) as batch_op:
        batch_op.drop_column('data')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('checkins', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))

    # ### end Alembic commands ###
