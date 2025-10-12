// src/components/tables/OpenOrdersTable.tsx

import { HTTP_BASE_URL } from '@/config'
import useIntersectionObserver from '@/hooks/useIntersectionObserver'
import type { OrderTableProps } from '@/lib/props/tableProps.'
import type { Order } from '@/lib/types/apiTypes/order'
import { OrderType } from '@/lib/types/orderType'
import { Side } from '@/lib/types/side'
import { cn, formatUnderscore } from '@/lib/utils'
import { Pencil, X } from 'lucide-react'
import React, { useCallback, useState, type FC } from 'react'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

// --- TYPE DEFINITIONS ---
type ModalState = { type: 'modify' | 'cancel'; order: Order } | null

// --- MODAL COMPONENTS (Simplified) ---

const ModifyModal: FC<{
    order: Order
    onSubmit: (data: { limit_price?: number; stop_price?: number }) => Promise<boolean>
    onClose: () => void
    error: string | null
}> = ({ order, onSubmit, onClose, error }) => {
    const [isSubmitting, setIsSubmitting] = useState(false)
    const isModifiable =
        order.order_type === OrderType.LIMIT || order.order_type === OrderType.STOP

    const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        if (!isModifiable) return

        setIsSubmitting(true)
        const formData = new FormData(e.currentTarget)
        const payload: { limit_price?: number; stop_price?: number } = {}

        if (order.order_type === OrderType.LIMIT) {
            const limitPrice = parseFloat(formData.get('limit_price') as string)
            if (!isNaN(limitPrice) && limitPrice > 0) payload.limit_price = limitPrice
        } else if (order.order_type === OrderType.STOP) {
            const stopPrice = parseFloat(formData.get('stop_price') as string)
            if (!isNaN(stopPrice) && stopPrice > 0) payload.stop_price = stopPrice
        }

        const success = await onSubmit(payload)
        if (success) onClose()
        else setIsSubmitting(false)
    }

    return (
        <div className="z-50 fixed inset-0 flex justify-center items-center bg-black/60">
            <form onSubmit={handleSubmit} className="w-[400px] p-6 border border-neutral-800 rounded-xl space-y-4 shadow-lg bg-background">
                <h2 className="text-lg font-semibold">Modify Order: {order.instrument_id}</h2>
                {isModifiable ? (
                    <>
                        {order.order_type === OrderType.LIMIT && (
                            <div>
                                <label className="block text-sm mb-1 text-muted-foreground">New Limit Price</label>
                                <Input type="number" name="limit_price" defaultValue={order.limit_price ?? ''} step="any" min="0" required disabled={isSubmitting} />
                            </div>
                        )}
                        {order.order_type === OrderType.STOP && (
                            <div>
                                <label className="block text-sm mb-1 text-muted-foreground">New Stop Price</label>
                                <Input type="number" name="stop_price" defaultValue={order.stop_price ?? ''} step="any" min="0" required disabled={isSubmitting} />
                            </div>
                        )}
                    </>
                ) : ( <p className="text-sm text-muted-foreground">Market orders cannot be modified.</p> )}
                {error && ( <div className="text-center text-red-500 text-sm p-2 bg-red-500/10 rounded-md">{error}</div> )}
                <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" onClick={onClose} variant="ghost" disabled={isSubmitting}>Cancel</Button>
                    {isModifiable && ( <Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Submitting...' : 'Submit Changes'}</Button> )}
                </div>
            </form>
        </div>
    )
}

const CancelModal: FC<{
    order: Order
    onSubmit: () => Promise<boolean>
    onClose: () => void
    error: string | null
}> = ({ order, onSubmit, onClose, error }) => {
    const [isSubmitting, setIsSubmitting] = useState(false)

    const handleConfirm = async () => {
        setIsSubmitting(true)
        const success = await onSubmit()
        if (success) onClose()
        else setIsSubmitting(false)
    }

    return (
        <div className="z-50 fixed inset-0 flex justify-center items-center bg-black/60">
            <div className="w-[400px] p-6 border border-neutral-800 rounded-xl space-y-4 shadow-lg bg-background">
                <h2 className="text-lg font-semibold">Cancel Order Confirmation</h2>
                <p className="text-sm text-muted-foreground">
                    Are you sure you want to cancel your{' '} {formatUnderscore(order.order_type)} order for{' '} <span className="font-semibold text-white">{order.quantity} of {order.instrument_id}</span>?
                </p>
                {error && ( <div className="text-center text-red-500 text-sm p-2 bg-red-500/10 rounded-md">{error}</div> )}
                <div className="flex justify-end gap-2 pt-2">
                    <Button type="button" onClick={onClose} variant="ghost" disabled={isSubmitting}>Back</Button>
                    <Button type="button" onClick={handleConfirm} variant="destructive" disabled={isSubmitting}>{isSubmitting ? 'Cancelling...' : 'Confirm Cancel'}</Button>
                </div>
            </div>
        </div>
    )
}

// --- ORDER DETAIL ROW (Restored Original Style) ---

const OrderDetailRow: FC<{
    order: Order
    showActions: boolean
    onModify: () => void
    onCancel: () => void
}> = ({ order, showActions, onModify, onCancel }) => (
    <tr className="border-t border-neutral-800 bg-neutral-900/50">
        <td colSpan={showActions ? 7 : 6} className="p-4">
            <div className="space-y-4">
                <div className="w-full flex justify-between">
                    <div className="flex flex-col">
                        <span className="w-fit text-md font-bold mb-1">{order.instrument_id}</span>
                        <div className="flex flex-row gap-2">
                            <span className={`w-fit py-1 px-2 rounded-sm text-xs ${order.side === Side.BID ? 'bg-green-500/20 text-[var(--green)]' : 'bg-red-500/20 text-[var(--red)]'}`}>
                                {formatUnderscore(order.side)}
                            </span>
                            <span className="w-fit py-1 px-2 rounded-sm text-xs bg-neutral-500/10 text-neutral-500">
                                {formatUnderscore(order.order_type)} Order
                            </span>
                        </div>
                    </div>
                    <span className="text-neutral-500 text-xs">{new Date(order.created_at).toLocaleString()}</span>
                </div>
                <div className="w-full flex justify-between items-end">
                    <div className="flex flex-row justify-start gap-x-8 gap-y-2 flex-wrap">
                        {[
                            { label: 'Avg Filled Price', value: order.avg_fill_price },
                            { label: 'Limit Price', value: order.limit_price },
                            { label: 'Stop Price', value: order.stop_price },
                            { label: 'Executed Quantity', value: order.executed_quantity },
                        ].map(({ label, value }) => (
                            <div key={label} className="flex flex-col">
                                <span className="text-xs text-neutral-400 whitespace-nowrap">{label}</span>
                                <span className="text-sm text-white">{typeof value === 'number' ? value : '--'}</span>
                            </div>
                        ))}
                    </div>
                    {showActions && (
                        <div className="flex flex-row items-center justify-end gap-3">
                            <Button type="button" disabled={order.order_type === OrderType.MARKET} onClick={onModify} className="h-8 w-20 rounded-md">Modify</Button>
                            <Button type="button" onClick={onCancel} variant="destructive" className="h-8 w-20 rounded-md">Cancel</Button>
                        </div>
                    )}
                </div>
            </div>
        </td>
    </tr>
)

// --- MAIN COMPONENT ---

const OpenOrdersTable: FC<OrderTableProps & { showActions: boolean }> = ({
    orders,
    onScrollEnd,
    showActions = true,
}) => {
    const [modalState, setModalState] = useState<ModalState>(null)
    const [focusedOrder, setFocusedOrder] = useState<Order | null>(null)
    const [error, setError] = useState<string | null>(null)
    const tableBottomRef = useIntersectionObserver(onScrollEnd)

    const handleRowClick = useCallback((order: Order) => {
        setFocusedOrder((prev) => (prev?.order_id === order.order_id ? null : order))
    }, [])
    
    const closeModal = () => {
        setModalState(null)
        setError(null)
    }

    const handleApiAction = async (action: () => Promise<Response>): Promise<boolean> => {
        setError(null)
        try {
            const response = await action()
            if (!response.ok) {
                const data = await response.json()
                throw new Error(data.detail || data.error || 'An unknown error occurred.')
            }
            return true
        } catch (err) {
            setError((err as Error).message)
            return false
        }
    }

    const handleModifyOrder = async (orderId: string, data: { limit_price?: number; stop_price?: number }) => {
        return handleApiAction(() => fetch(`${HTTP_BASE_URL}/orders/${orderId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(data),
        }))
    }

    const handleCancelOrder = async (orderId: string) => {
        return handleApiAction(() => fetch(`${HTTP_BASE_URL}/orders/${orderId}`, {
            method: 'DELETE',
            credentials: 'include',
        }))
    }

    return (
        <>
            {modalState?.type === 'modify' && (
                <ModifyModal order={modalState.order} onClose={closeModal} error={error} onSubmit={(data) => handleModifyOrder(modalState.order.order_id, data)} />
            )}
            {modalState?.type === 'cancel' && (
                <CancelModal order={modalState.order} onClose={closeModal} error={error} onSubmit={() => handleCancelOrder(modalState.order.order_id)} />
            )}
            <div className="w-full h-full overflow-auto">
                <table className="min-w-full text-sm text-left border-collapse">
                    <thead className="text-sm font-semibold">
                        <tr className="text-neutral-500">
                            <th>Symbol</th>
                            <th>Side</th>
                            <th>Type</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Status</th>
                            {showActions && <th className="text-right pr-4">Actions</th>}
                        </tr>
                    </thead>
                    <tbody>
                        {orders.length === 0 ? (
                            <tr><td colSpan={showActions ? 7 : 6} className="h-20 text-center"><span className="text-neutral-500">No open orders</span></td></tr>
                        ) : (
                            orders.map((order) => (
                                <React.Fragment key={order.order_id}>
                                    <tr className="h-10 border-t border-neutral-800 hover:bg-neutral-800/50 cursor-pointer" onClick={() => handleRowClick(order)}>
                                        <td>{order.instrument_id}</td>
                                        <td className={cn(order.side === Side.BID ? 'text-[var(--green)]' : 'text-[var(--red)]')}>{formatUnderscore(order.side)}</td>
                                        <td>{formatUnderscore(order.order_type)}</td>
                                        <td>{order.quantity}</td>
                                        <td>{order.limit_price ?? order.stop_price ?? '--'}</td>
                                        <td>{formatUnderscore(order.status)}</td>
                                        {showActions && (
                                            <td className="text-right pr-4">
                                                <div className="flex items-center justify-end gap-3">
                                                    <Pencil className={cn('size-4 cursor-pointer text-neutral-400 hover:text-white', order.order_type === OrderType.MARKET && 'cursor-not-allowed opacity-30')}
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            if (order.order_type !== OrderType.MARKET) setModalState({ type: 'modify', order })
                                                        }}
                                                    />
                                                    <X className="size-5 cursor-pointer text-neutral-400 hover:text-red-500"
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            setModalState({ type: 'cancel', order })
                                                        }}
                                                    />
                                                </div>
                                            </td>
                                        )}
                                    </tr>
                                    {focusedOrder?.order_id === order.order_id && (
                                        <OrderDetailRow order={order} showActions={showActions} onModify={() => setModalState({ type: 'modify', order })} onCancel={() => setModalState({ type: 'cancel', order })} />
                                    )}
                                </React.Fragment>
                            ))
                        )}
                    </tbody>
                </table>
                <div ref={tableBottomRef} className="h-1" />
            </div>
        </>
    )
}

export default OpenOrdersTable