import Header from '@/components/Header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { HTTP_BASE_URL } from '@/config'
import { Loader2 } from 'lucide-react'
import { type FC, type FormEvent, useEffect, useState } from 'react'

const InstrumentCreatePage: FC = () => {
    const [instrumentId, setInstrumentId] = useState('')
    const [symbol, setSymbol] = useState('')
    const [tickSize, setTickSize] = useState('1.0')

    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [successMessage, setSuccessMessage] = useState<string | null>(null)

    useEffect(() => {
        document.body.classList.add('bg-zinc-900')
        return () => {
            document.body.classList.remove('bg-zinc-900')
        }
    }, [])

    const clearForm = () => {
        setInstrumentId('')
        setSymbol('')
        setTickSize('1.0')
    }

    const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault()
        setIsLoading(true)
        setError(null)
        setSuccessMessage(null)

        if (!instrumentId || !symbol || !tickSize) {
            setError('All fields are required.')
            setIsLoading(false)
            return
        }

        const body = {
            instrument_id: instrumentId,
            symbol: symbol,
            tick_size: parseFloat(tickSize),
        }

        try {
            const rsp = await fetch(`${HTTP_BASE_URL}/instruments`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            })

            if (!rsp.ok) {
                const data = await rsp.json()
                const errorDetail =
                    data.detail || data.error || 'An unknown error occurred'
                throw new Error(
                    typeof errorDetail === 'string'
                        ? errorDetail
                        : JSON.stringify(errorDetail)
                )
            }

            setSuccessMessage(`${symbol} created successfully!`)
            clearForm()
        } catch (err) {
            setError((err as Error).message)
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="w-full min-h-screen text-white">
            <Header />

            <main className="w-full flex flex-col items-center justify-center pt-24 px-4">
                <div className="w-full max-w-lg bg-background rounded-lg shadow-lg p-8 border border-neutral-800">
                    <h1 className="text-2xl font-bold mb-2 text-center">
                        Create New Instrument
                    </h1>
                    <p className="text-sm text-muted-foreground text-center mb-8">
                        Define a new tradeable instrument for the exchange.
                    </p>

                    <form onSubmit={handleSubmit} className="space-y-6">
                        {/* Instrument ID Field */}
                        <div>
                            <label
                                htmlFor="instrument_id"
                                className="block text-sm font-medium text-muted-foreground mb-2"
                            >
                                Instrument ID
                            </label>
                            <Input
                                id="instrument_id"
                                name="instrument_id"
                                type="text"
                                placeholder="e.g., BTCUSD-SPOT"
                                value={instrumentId}
                                onChange={(e) =>
                                    setInstrumentId(e.target.value)
                                }
                                required
                                disabled={isLoading}
                            />
                            <p className="text-xs text-muted-foreground mt-2">
                                The unique identifier for the instrument. Should
                                be uppercase.
                            </p>
                        </div>

                        {/* Symbol Field */}
                        <div>
                            <label
                                htmlFor="symbol"
                                className="block text-sm font-medium text-muted-foreground mb-2"
                            >
                                Symbol
                            </label>
                            <Input
                                id="symbol"
                                name="symbol"
                                type="text"
                                placeholder="e.g., BTC/USD"
                                value={symbol}
                                onChange={(e) => setSymbol(e.target.value)}
                                required
                                disabled={isLoading}
                            />
                            <p className="text-xs text-muted-foreground mt-2">
                                The user-facing display symbol.
                            </p>
                        </div>

                        {/* Tick Size Field */}
                        <div>
                            <label
                                htmlFor="tick_size"
                                className="block text-sm font-medium text-muted-foreground mb-2"
                            >
                                Tick Size
                            </label>
                            <Input
                                id="tick_size"
                                name="tick_size"
                                type="number"
                                placeholder="1.0"
                                value={tickSize}
                                onChange={(e) => setTickSize(e.target.value)}
                                step="any"
                                min="0"
                                required
                                disabled={isLoading}
                            />
                            <p className="text-xs text-muted-foreground mt-2">
                                The minimum price fluctuation of the instrument.
                            </p>
                        </div>

                        {/* Status Messages */}
                        {error && (
                            <div className="text-red-500 text-sm text-center p-1 rounded-md">
                                {error}
                            </div>
                        )}
                        {successMessage && (
                            <div className="text-green-500 text-sm text-center p-1 rounded-md">
                                {successMessage}
                            </div>
                        )}

                        {/* Submit Button */}
                        <Button
                            type="submit"
                            className="w-full text-white bg-neutral-800 hover:bg-neutral-900 hover:scale-101 cursor-pointer"
                            disabled={isLoading}
                        >
                            {isLoading && (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            )}
                            {isLoading ? 'Creating...' : 'Create Instrument'}
                        </Button>
                    </form>
                </div>
            </main>
        </div>
    )
}

export default InstrumentCreatePage
