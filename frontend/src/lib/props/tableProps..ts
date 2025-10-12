import type { Order } from '../types/apiTypes/order'

export interface TableProps {
    onScrollEnd: () => void
}

export interface OrderTableProps extends TableProps {
    orders: Order[]
}
