import Header from '@/components/Header'
import OrderHistoryTable from '@/components/tables/OrderHistoryTable'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { HTTP_BASE_URL } from '@/config'
import type { Order } from '@/lib/types/apiTypes/order'
import type { PaginatedResponse } from '@/lib/types/apiTypes/paginatedResponse'
import { AreaSeries, createChart, type ISeriesApi } from 'lightweight-charts'
import { ChevronUp } from 'lucide-react'
import { useEffect, useRef, useState, type FC } from 'react'

// Types
type UserOverview = {
    cash_balance: number
    portfolio_balance: number
    data: { [key: string]: number }
}
const tableTabs = ['history']
type Tab = (typeof tableTabs)[number]
interface BalanceItem {
    time: string
    value: number
}

const BalanceChart: FC = () => {
    const chartContainerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<ReturnType<typeof createChart> | null>(null)
    const areaSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)

    const [data, setData] = useState<BalanceItem[]>([])

    useEffect(() => {
        const fetchBalanceHistory = async () => {
            const rsp = await fetch(
                HTTP_BASE_URL + '/user/history?interval=1d',
                {
                    credentials: 'include',
                }
            )
            if (rsp.ok) {
                const data = await rsp.json()
                const formattedData = data.map((d: BalanceItem) => ({
                    time: Math.floor(new Date(d.time).getTime() / 1000),
                    value: d.value,
                }))
                setData(formattedData)
            }
        }

        fetchBalanceHistory()
    }, [])

    useEffect(() => {
        if (!chartContainerRef.current) return

        chartRef.current = createChart(chartContainerRef.current, {
            layout: {
                background: { color: 'transparent' },
                textColor: 'white',
                attributionLogo: false,
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { visible: false },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                borderColor: '#ccc',
            },
            rightPriceScale: {
                borderColor: '#ccc',
            },
            localization: {
                priceFormatter: (price: number) =>
                    `$${price.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                    })}`,
            },
        })

        areaSeriesRef.current = chartRef.current.addSeries(AreaSeries)
        chartRef.current.timeScale().fitContent()
    }, [])

    useEffect(() => {
        if (data.length && areaSeriesRef.current) {
            areaSeriesRef.current.setData(data)
        }
    }, [data])

    return (
        <div className="w-full h-full flex flex-col bg-transparent border-none">
            <div className="flex items-center gap-2 space-y-0 sm:flex-row mb-4">
                <div className="flex-1">
                    <h2 className="text-lg font-semibold">Balance History</h2>
                    <p className="text-sm text-gray-500">
                        Showing balance over time
                    </p>
                </div>
            </div>
            <div className="flex-1 w-full">
                <div ref={chartContainerRef} className="w-full h-full" />
            </div>
        </div>
    )
}

const UserOverviewPage: FC = () => {
    const pageNumRef = useRef<number>(0)

    const [userOverview, setUserOverview] = useState<UserOverview | undefined>(
        undefined
    )

    const [tableTab, setTableTab] = useState<Tab>('history')
    const [orderHistory, setOrderHistory] = useState<Order[]>([])
    const [showScrollToTop, setShowScollToTop] = useState<boolean>(false)
    const [isLoading, setIsLoading] = useState<boolean>(false)

    useEffect(() => {
        const scrollEvent = () =>
            setShowScollToTop(window.scrollY > window.innerHeight)

        document.body.classList.add('bg-zinc-900')
        document.addEventListener('scroll', scrollEvent)

        return () => {
            document.body.classList.remove('bg-zinc-900')
            document.removeEventListener('scroll', () => scrollEvent)
        }
    }, [])

    useEffect(() => {
        const fetchUserSummary = async () => {
            const rsp = await fetch(HTTP_BASE_URL + '/user', {
                credentials: 'include',
            })

            if (rsp.ok) {
                const data: UserOverview = await rsp.json()
                setUserOverview(data)
            } else {
                console.error("Error fetching user summary.", rsp)
            }
        }

        fetchUserSummary()
    }, [])

    async function fetchOrderHistory(): Promise<void> {
        if (pageNumRef.current == 1) {
            setIsLoading(true)
        }

        const params = new URLSearchParams()

        params.append('page', pageNumRef.current.toString())

        const rsp = await fetch(HTTP_BASE_URL + `/orders?${params}`, {
            credentials: 'include',
        })
        if (rsp.ok) {
            const data: PaginatedResponse<Order> = await rsp.json()
            setOrderHistory((prev) => [...prev, ...data.data])
        }

        if (pageNumRef.current == 1) {
            setIsLoading(false)
        }
    }

    return (
        <>
            <Header />
            <main className="mt-11 pb-5">
                <div className="max-w-5xl h-fit mx-auto">
                    <section className="w-full mb-1">
                        <div className="flex flex-col lg:flex-row gap-4">
                            <div className="flex flex-col justify-between min-w-[300px] max-w-full h-fit max-h-fit bg-background border border-zinc-800 rounded-xl px-6 py-5">
                                {/* Balance */}
                                <div className="flex flex-col mb-3">
                                    <span className="text-xs text-zinc-400 uppercase tracking-wide">
                                        Portfolio Balance
                                    </span>
                                    {userOverview ? (
                                        <span className="text-2xl font-bold text-white">
                                            $
                                            {userOverview.portfolio_balance.toLocaleString(
                                                undefined,
                                                { minimumFractionDigits: 2 }
                                            )}
                                        </span>
                                    ) : (
                                        <Skeleton className="w-32 h-10 mt-2" />
                                    )}
                                </div>
                            </div>

                            {/* Balance Chart Container */}
                            <div className="flex-1 h-100 p-3 bg-background border border-zinc-800 rounded-xl">
                                <BalanceChart />
                            </div>
                        </div>
                    </section>

                    {/* Tables */}
                    <section className="min-h-150 border border-zinc-800 rounded-xl bg-background overflow-hidden p-1">
                        {isLoading ? (
                            <Skeleton className="w-full h-ull" />
                        ) : (
                            <>
                                <div className="w-full mb-2 flex items-center justify-start p-3">
                                    {tableTabs.map((tab) => (
                                        <Button
                                            type="button"
                                            className={`bg-transparent hover:bg-transparent rounded-none border-b-2 hover:text-white cursor-pointer ${tableTab == tab ? 'border-b-white text-white' : 'border-b-transparent text-neutral-900'}`}
                                            onClick={() => {
                                                pageNumRef.current = 1
                                                setTableTab(tab)
                                            }}
                                        >
                                            {tab.charAt(0).toUpperCase() +
                                                tab.slice(1)}
                                        </Button>
                                    ))}
                                </div>
                                <div className="w-full p-3">
                                    <OrderHistoryTable
                                        orders={orderHistory}
                                        onScrollEnd={() => {
                                            pageNumRef.current += 1
                                            fetchOrderHistory()
                                        }}
                                    />
                                </div>
                            </>
                        )}
                    </section>
                </div>
            </main>

            <div
                className={`fixed w-10 h-10 bottom-12 right-10 flex items-center justify-center rounded-full bg-gray-900 cursor-pointer transition-all duration-300 ${showScrollToTop ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-100'}`}
                onClick={() => window.scrollTo({ top: 0 })}
            >
                <ChevronUp className="size-5" />
            </div>
        </>
    )
}

export default UserOverviewPage
