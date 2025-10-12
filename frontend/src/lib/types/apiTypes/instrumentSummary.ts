export interface BaseInstrumentSummary {
    price?: number
    change_24h?: number
}

export interface InstrumentSummary extends BaseInstrumentSummary {
    instrument: string
}

export interface Instrument24h {
  h24_volume: number;
  h24_change: number;
  h24_high: number;
  h24_low: number;
}
