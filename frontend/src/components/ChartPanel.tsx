import { TimeFrame } from '@/lib/types/timeframe'
import {
    CandlestickSeries,
    ColorType,
    createChart,
    type CandlestickData,
    type IChartApi,
    type ISeriesApi,
    type Time,
} from 'lightweight-charts'
import { ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState, type FC, type RefObject } from 'react'
import InstrumentSelector from './InstrumentSelector'
import Logo from './Logo'
import { Button } from './ui/button'

const ChartPanel: FC<{
    instrument: string
    price?: number | null
    prevPrice?: number | null
    h24_change?: number | null
    h24_high?: number | null
    h24_low?: number | null
    h24_volume?: number | null
    candles: CandlestickData<Time>[]
    seriesRef: React.RefObject<ISeriesApi<'Candlestick'> | null>
    defaultTimeFrame?: TimeFrame
    onTimeFrameChange: (value: TimeFrame) => void
    onInstrumentSelect: (instrumentId: string) => void
}> = ({
    instrument,
    price,
    prevPrice,
    h24_change,
    h24_high,
    h24_low,
    h24_volume,
    candles,
    seriesRef,
    defaultTimeFrame = TimeFrame.M5,
    onTimeFrameChange = () => {},
    onInstrumentSelect,
}) => {
    const containerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi>(null)
    const [timeFrame, _setCurrentTimeFrame] =
        useState<TimeFrame>(defaultTimeFrame)
    const [isLoading, setIsLoading] = useState<boolean>(true)
    const [isSelectorOpen, setIsSelectorOpen] = useState(false)
    const triggerRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!containerRef.current) return

        setIsLoading(true)

        if (!chartRef.current) {
            chartRef.current = createChart(containerRef.current, {
                autoSize: true,
                layout: {
                    background: {
                        type: ColorType.Solid,
                        color: 'transparent',
                    },
                    textColor: 'white',
                },
                grid: {
                    vertLines: { color: '#151515' },
                    horzLines: { color: '#151515' },
                },
                timeScale: {
                    timeVisible: true,
                },
            })
        }

        if (!seriesRef.current) {
            seriesRef.current = chartRef.current.addSeries(CandlestickSeries)
        }

        seriesRef.current.setData(candles)

        setIsLoading(false)
    }, [containerRef, candles])

    const setTimeFrame = (val: TimeFrame): void => {
        onTimeFrameChange(val)
        _setCurrentTimeFrame(val)
    }

    return (
        <div className="w-full h-full flex flex-col p-5 gap-1">
            <div className="w-full h-15 flex flex-row items-center justify-start">
                <div
                    ref={triggerRef}
                    onMouseUp={() => setIsSelectorOpen(!isSelectorOpen)}
                    className="w-fit h-full flex items-center px-2 text-left border-r border-neutral-800 cursor-pointer"
                >
                    <div className="flex flex-col pr-2">
                        <span className="font-bold text-sm whitespace-nowrap">
                            {instrument}
                        </span>
                        <span
                            className={`
                            font-semibold
                            ${
                                typeof price == 'number' &&
                                typeof prevPrice === 'number'
                                    ? price >= prevPrice
                                        ? 'text-[var(--green)]'
                                        : 'text-[var(--red)]'
                                    : ''
                            }
                        `}
                        >
                            {typeof price === 'number' ? price : '-'}
                        </span>
                    </div>
                    <ChevronDown className="size-4 text-muted-foreground" />
                </div>
                <InstrumentSelector
                    isOpen={isSelectorOpen}
                    onClose={() => setIsSelectorOpen(false)}
                    onSelect={onInstrumentSelect}
                    triggerRef={triggerRef as RefObject<HTMLDivElement>}
                />

                <div className="w-30 h-full flex items-center justify-center px-2 ">
                    <div className="flex flex-col">
                        <span className="font-bold text-right text-sm text-neutral-500">
                            24h Change
                        </span>
                        <span
                            className={`
                            text-right
                            font-semibold
                            text-sm
                            ${
                                typeof h24_change === 'number'
                                    ? h24_change >= 0
                                        ? 'text-[var(--green)]'
                                        : 'text-[var(--red)]'
                                    : ''
                            }
                        `}
                        >
                            {typeof h24_change === 'number'
                                ? `${h24_change.toFixed(2)}%`
                                : '-'}
                        </span>
                    </div>
                </div>

                <div className="w-30 h-full flex items-center justify-center px-2 ">
                    <div className="flex flex-col">
                        <span className="font-bold text-right text-sm text-neutral-500">
                            24h High
                        </span>
                        <span className="text-right font-semibold text-sm">
                            {typeof h24_high === 'number'
                                ? h24_high.toFixed(2)
                                : '-'}
                        </span>
                    </div>
                </div>

                <div className="w-30 h-full flex items-center justify-center px-2  ">
                    <div className="flex flex-col">
                        <span className="font-bold text-right text-sm text-neutral-500">
                            24h Low
                        </span>
                        <span className="text-right font-semibold text-sm">
                            {typeof h24_low === 'number'
                                ? h24_low.toFixed(2)
                                : '-'}
                        </span>
                    </div>
                </div>

                <div className="w-30 h-full flex items-center justify-center px-2 ">
                    <div className="flex flex-col">
                        <span className="font-bold text-right text-sm text-neutral-500">
                            24h Volume
                        </span>
                        <span className="text-right font-semibold text-sm">
                            {typeof h24_volume === 'number'
                                ? h24_volume.toFixed(2)
                                : '-'}
                        </span>
                    </div>
                </div>
            </div>
            <div className="w-full h-10 flex flex-row items-center justify-start gap-3">
                {Object.values(TimeFrame).map((val) => (
                    <Button
                        key={val}
                        type="button"
                        className={`bg-transparent hover:bg-transparent rounded-none border-b-1 border-b-transparent cursor-pointer transition-border-b duration-300 ${timeFrame === val ? 'border-b-blue-500 text-white' : 'hover:border-b-blue-600 text-neutral-900'}`}
                        onClick={() => setTimeFrame(val as TimeFrame)}
                    >
                        {val}
                    </Button>
                ))}
            </div>
            <div
                ref={containerRef}
                className="w-full flex-1 relative text-center"
            >
                {isLoading && (
                    <div className="z-[3] absolute top-0 left-0 w-full h-full flex items-center justify-center bg-background">
                        <Logo />
                    </div>
                )}
            </div>
        </div>
    )
}
export default ChartPanel
