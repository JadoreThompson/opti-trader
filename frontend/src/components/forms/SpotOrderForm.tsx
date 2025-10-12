import { HTTP_BASE_URL } from '@/config'
import {
    OCOOrderCreate,
    OrderCreate,
    OTOOrderCreate,
    type OrderCreateType,
} from '@/lib/types/formTypes/order'
import { OrderType } from '@/lib/types/orderType'
import { Side } from '@/lib/types/side'
import { cn } from '@/lib/utils'
import { AssertError, Value } from '@sinclair/typebox/value'
import { Info } from 'lucide-react'
import { useState, type FC } from 'react'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '../ui/select'
import { Tabs, TabsList, TabsTrigger } from '../ui/tabs'

const OCOFields = () => {
    const [firstOrderType, setFirstOrderType] = useState<OrderType>(
        OrderType.LIMIT
    )
    const [secondOrderType, setSecondOrderType] = useState<OrderType>(
        OrderType.STOP
    )

    return (
        <>
            <div className="relative flex text-xs text-muted-foreground mb-3 font-medium">
                OCO Orders (Both orders will be placed){' '}
                <Info className="info ml-2 w-4 h-4 text-blue-600 dark:text-blue-400" />
                <div className="order-type-info hidden z-999 absolute top-5 w-full p-3 bg-blue-50 dark:bg-blue-950/30 backdrop-blur-2xl border border-blue-200 dark:border-blue-800 rounded-lg">
                    <div className="flex items-start gap-2">
                        <div className="text-xs text-blue-700 dark:text-blue-300">
                            <div>
                                <strong>OCO (One-Cancels-Other):</strong> Places
                                two orders simultaneously. When one executes,
                                the other is automatically cancelled.
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div className="grid grid-cols-1 gap-3">
                <div>
                    <span className="text-sm">First Order</span>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            Order Type
                        </label>
                        <Select
                            name="first_order_type"
                            value={firstOrderType}
                            onValueChange={(val) =>
                                setFirstOrderType(val as OrderType)
                            }
                        >
                            <SelectTrigger className="h-9 w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={OrderType.LIMIT}>
                                    Limit
                                </SelectItem>

                                <SelectItem value={OrderType.STOP}>
                                    Stop
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            {firstOrderType === OrderType.LIMIT
                                ? 'Limit Price'
                                : 'Stop Price'}
                        </label>
                        <Input
                            type="number"
                            name="first_order_price"
                            className="h-9"
                            step={0.01}
                            required
                        />
                    </div>
                </div>
            </div>

            <div>
                <div>
                    <span className="text-sm">Second Order</span>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            Order Type
                        </label>
                        <Select
                            name="second_order_type"
                            value={secondOrderType}
                            onValueChange={(val) =>
                                setSecondOrderType(val as OrderType)
                            }
                        >
                            <SelectTrigger className="h-9 w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={OrderType.LIMIT}>
                                    Limit
                                </SelectItem>

                                <SelectItem value={OrderType.STOP}>
                                    Stop
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            {secondOrderType === OrderType.LIMIT
                                ? 'Limit Price'
                                : 'Stop Price'}
                        </label>
                        <Input
                            type="number"
                            name="second_order_price"
                            className="h-9"
                            step={0.01}
                            required
                        />
                    </div>
                </div>
            </div>
        </>
    )
}

const OTOFields = () => {
    const [firstOrderType, setFirstOrderType] = useState<OrderType>(
        OrderType.LIMIT
    )
    const [secondOrderType, setSecondOrderType] = useState<OrderType>(
        OrderType.LIMIT
    )

    return (
        <>
            <div className="relative flex text-xs text-muted-foreground mb-3 font-medium">
                OTO Orders (First order triggers second order){' '}
                <Info className="info ml-2 w-4 h-4 text-blue-600 dark:text-blue-400" />
                <div className="order-type-info hidden z-999 absolute top-5 w-full p-3 bg-blue-50 dark:bg-blue-950/30 backdrop-blur-2xl border border-blue-200 dark:border-blue-800 rounded-lg">
                    <div className="flex items-start gap-2">
                        <div className="text-xs text-blue-700 dark:text-blue-300">
                            <div>
                                <strong>OTO (One-Triggers-Other):</strong>{' '}
                                Places a trigger order that, when executed,
                                automatically places a secondary order.
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div className="grid grid-cols-1 gap-3">
                <div>
                    <span className="text-sm">Trigger Order</span>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            Order Type
                        </label>
                        <Select
                            name="first_order_type"
                            value={firstOrderType}
                            onValueChange={(val) =>
                                setFirstOrderType(val as OrderType)
                            }
                        >
                            <SelectTrigger className="h-9 w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={OrderType.LIMIT}>
                                    Limit
                                </SelectItem>
                                <SelectItem value={OrderType.MARKET}>
                                    Market
                                </SelectItem>
                                <SelectItem value={OrderType.STOP}>
                                    Stop
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            {firstOrderType === OrderType.LIMIT
                                ? 'Limit Price'
                                : firstOrderType === OrderType.STOP
                                  ? 'Stop Price'
                                  : 'Price'}
                        </label>
                        <Input
                            type="number"
                            name="first_order_price"
                            className="h-9"
                            step={0.01}
                            disabled={firstOrderType === OrderType.MARKET}
                            required
                        />
                    </div>
                </div>
            </div>

            <div>
                <div>
                    <span className="text-sm">Pending Order</span>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            Order Type
                        </label>
                        <Select
                            name="second_order_type"
                            value={secondOrderType}
                            onValueChange={(val) =>
                                setSecondOrderType(val as OrderType)
                            }
                        >
                            <SelectTrigger className="h-9 w-full">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value={OrderType.LIMIT}>
                                    Limit
                                </SelectItem>
                                <SelectItem value={OrderType.STOP}>
                                    Stop
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <label className="text-xs text-muted-foreground">
                            {secondOrderType === OrderType.LIMIT
                                ? 'Limit Price'
                                : secondOrderType === OrderType.STOP
                                  ? 'Stop Price'
                                  : 'Price'}
                        </label>
                        <Input
                            type="number"
                            name="second_order_price"
                            className="h-9"
                            step={0.01}
                            disabled={secondOrderType === OrderType.MARKET}
                            required
                        />
                    </div>
                </div>
            </div>
        </>
    )
}

type FormDataMap = Record<string, FormDataEntryValue>
type CommonOrderProperties = {
    instrument_id: string
    side: Side
    quantity: number
}

const createOrderLeg = (
    type: OrderType,
    priceStr: string | undefined,
    common: CommonOrderProperties
): Partial<OrderCreateType> => {
    const order: Partial<OrderCreateType> = { ...common, order_type: type }

    if (priceStr) {
        if (type === OrderType.LIMIT) order.limit_price = parseFloat(priceStr)
        else if (type === OrderType.STOP)
            order.stop_price = parseFloat(priceStr)
    }
    return order
}

const buildStandardOrderBody = (
    formData: FormDataMap,
    common: CommonOrderProperties,
    orderType: OrderType
) => {
    return createOrderLeg(
        orderType,
        (formData.limit_price || formData.stop_price) as string,
        common
    )
}

const buildOcoOrderBody = (
    formData: FormDataMap,
    common: CommonOrderProperties
) => {
    return {
        legs: [
            createOrderLeg(
                formData.first_order_type as OrderType,
                formData.first_order_price as string,
                common
            ),
            createOrderLeg(
                formData.second_order_type as OrderType,
                formData.second_order_price as string,
                common
            ),
        ],
    }
}

const buildOtoOrderBody = (
    formData: FormDataMap,
    common: CommonOrderProperties
) => {
    return {
        parent: createOrderLeg(
            formData.first_order_type as OrderType,
            formData.first_order_price as string,
            common
        ),
        child: createOrderLeg(
            formData.second_order_type as OrderType,
            formData.second_order_price as string,
            common
        ),
    }
}

/**
 * Supports Market, Limit, Stop, OCO, and OTO Orders for Spot trading.
 */
const SpotOrderForm: FC<{
    balance?: number | null
    assetBalance?: number | null
    instrument: string
    setBalance: React.Dispatch<React.SetStateAction<number>>
}> = ({
    balance,
    assetBalance: asset_balance,
    instrument,
    setBalance,
}) => {
    const [side, setSide] = useState<Side>(Side.BID)
    const [orderType, setOrderType] = useState<OrderType>(OrderType.LIMIT)
    const [errorMsg, setErrorMsg] = useState<string | null>(null)

    const sideColor =
        side === Side.BID
            ? 'bg-green-600 hover:bg-green-700'
            : 'bg-red-600 hover:bg-red-700'

    const isOCOOrder = orderType === OrderType.OCO
    const isOTOOrder = orderType === OrderType.OTO

    const getButtonLabel = () => {
        const sideText = side === Side.BID ? 'Buy' : 'Sell'
        switch (orderType) {
            case OrderType.MARKET:
                return `${sideText} Market`
            case OrderType.LIMIT:
                return `${sideText} Limit`
            case OrderType.STOP:
                return `${sideText} Stop`
            case OrderType.OCO:
                return `${sideText} OCO`
            case OrderType.OTO:
                return `${sideText} OTO`
            default:
                return `${sideText} Order`
        }
    }

    const getSchemaForOrderType = () => {
        switch (orderType) {
            case OrderType.MARKET:
            case OrderType.LIMIT:
            case OrderType.STOP:
                return OrderCreate
            case OrderType.OCO:
                return OCOOrderCreate
            case OrderType.OTO:
                return OTOOrderCreate
            default:
                return OrderCreate
        }
    }

    const handleFormSubmit = async (
        e: React.FormEvent<HTMLFormElement>
    ): Promise<void> => {
        e.preventDefault()
        setErrorMsg(null)

        const formData = Object.fromEntries(
            new FormData(e.currentTarget).entries()
        )

        try {
            const commonOrderProperties: CommonOrderProperties = {
                instrument_id: instrument,
                side,
                quantity: parseFloat(formData.quantity as string),
            }

            let rawBody: unknown
            if (isOCOOrder) {
                rawBody = buildOcoOrderBody(formData, commonOrderProperties)
            } else if (isOTOOrder) {
                rawBody = buildOtoOrderBody(formData, commonOrderProperties)
            } else {
                rawBody = buildStandardOrderBody(
                    formData,
                    commonOrderProperties,
                    orderType
                )
            }

            const schema = getSchemaForOrderType()
            const body = Value.Parse(schema, rawBody)

            let suffix = ''
            if (orderType === OrderType.OCO) {
                suffix = '/oco'
            } else if (orderType === OrderType.OTO) {
                suffix = '/oto'
            }

            const rsp = await fetch(`${HTTP_BASE_URL}/orders${suffix}`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            })

            const data = await rsp.json()

            if (!rsp.ok) {
                const errorDetail =
                    data.detail || data.error || 'An unknown error occurred'
                throw new Error(
                    typeof errorDetail === 'string'
                        ? errorDetail
                        : JSON.stringify(errorDetail)
                )
            }

            setBalance(data['available_balance'])
        } catch (error) {
            if (error instanceof AssertError) {
                // Validation error from TypeBox
                const firstError = error.errors[0]
                const fieldName = firstError.path
                    .substring(1)
                    .replace(/\//g, ' -> ')
                console.error('Validation Errors:', Array.from(error.errors))
                setErrorMsg(
                    `Invalid input for '${fieldName}': ${firstError.message}`
                )
            } else {
                // Error from fetch or other issues
                setErrorMsg((error as Error).message)
            }
        }
    }

    return (
        <div className="min-h-[600px]">
            <form onSubmit={handleFormSubmit} className="w-full">
                <div className="w-full rounded-xl border-none p-4">
                    {/* Side Switch Tabs */}
                    <Tabs
                        defaultValue={side}
                        onValueChange={(val) => setSide(val as Side)}
                    >
                        <TabsList className="flex items-center w-full mb-4">
                            <TabsTrigger
                                type="button"
                                value={Side.BID}
                                className="rounded-l-md data-[state=active]:bg-green-600 data-[state=active]:text-white bg-transparent cursor-pointer"
                            >
                                Buy
                            </TabsTrigger>
                            <TabsTrigger
                                type="button"
                                value={Side.ASK}
                                className="rounded-r-md data-[state=active]:bg-red-600 data-[state=active]:text-white cursor-pointer"
                            >
                                Sell
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>

                    {/* Order Type Dropdown */}
                    <div className="mb-4">
                        <label className="text-xs text-muted-foreground mb-2 block">
                            Order Type
                        </label>
                        <Select
                            value={orderType}
                            onValueChange={(value) =>
                                setOrderType(value as OrderType)
                            }
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select order type" />
                            </SelectTrigger>
                            <SelectContent className="max-h-[200px] overflow-y-auto">
                                <SelectItem value={OrderType.MARKET}>
                                    Market
                                </SelectItem>
                                <SelectItem value={OrderType.LIMIT}>
                                    Limit
                                </SelectItem>
                                <SelectItem value={OrderType.STOP}>
                                    Stop
                                </SelectItem>
                                <SelectItem value={OrderType.OCO}>
                                    <div className="flex items-center gap-2">
                                        OCO
                                        <Badge
                                            variant="secondary"
                                            className="text-xs"
                                        >
                                            Advanced
                                        </Badge>
                                    </div>
                                </SelectItem>
                                <SelectItem value={OrderType.OTO}>
                                    <div className="flex items-center gap-2">
                                        OTO
                                        <Badge
                                            variant="secondary"
                                            className="text-xs"
                                        >
                                            Advanced
                                        </Badge>
                                    </div>
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Order Form */}
                    <div className="space-y-4 mb-2">
                        {/* Standard Order Fields */}
                        {orderType === OrderType.LIMIT && (
                            <div>
                                <label className="text-xs text-muted-foreground">
                                    Limit Price
                                </label>
                                <Input
                                    type="number"
                                    name="limit_price"
                                    placeholder="0.00"
                                    className="h-9"
                                    step={0.01}
                                    required
                                />
                            </div>
                        )}

                        {orderType === OrderType.STOP && (
                            <div>
                                <label className="text-xs text-muted-foreground">
                                    Stop Price
                                </label>
                                <Input
                                    type="number"
                                    name="stop_price"
                                    placeholder="0.00"
                                    className="h-9"
                                    step={0.01}
                                    required
                                />
                            </div>
                        )}

                        {/* OCO Order Fields */}
                        {isOCOOrder && <OCOFields />}

                        {/* OTO Order Fields */}
                        {isOTOOrder && <OTOFields />}

                        {/* Quantity Field */}
                        <div>
                            <div className="flex justify-between text-xs text-muted-foreground mb-1">
                                <span>Quantity</span>
                                {side === Side.BID ? (
                                    <span>
                                        Available:{' '}
                                        {typeof balance === 'number'
                                            ? balance.toFixed(2)
                                            : '-'}{' '}
                                        USDT
                                    </span>
                                ) : (
                                    <span>
                                        Available:{' '}
                                        {typeof asset_balance === 'number'
                                            ? asset_balance.toFixed(2)
                                            : '-'}{' '}
                                        {instrument}
                                    </span>
                                )}
                            </div>
                            <Input
                                type="number"
                                name="quantity"
                                placeholder="0.00"
                                className="h-9"
                                step="any"
                                required
                            />
                        </div>
                    </div>

                    {errorMsg && (
                        <div className="w-full text-center mb-2">
                            <span className="text-red-500 text-sm">
                                {errorMsg}
                            </span>
                        </div>
                    )}

                    {/* Submit Button */}
                    <Button
                        type="submit"
                        disabled={balance === null}
                        className={cn(
                            'w-full text-white cursor-pointer',
                            sideColor
                        )}
                    >
                        {getButtonLabel()}
                    </Button>
                </div>
            </form>
        </div>
    )
}

export default SpotOrderForm
