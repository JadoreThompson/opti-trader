import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { DollarSign } from "lucide-react";
import { type FC, useMemo, useState } from "react";

// --- Types Definition ---

interface AssetHolding {
  id: number;
  instrument: string; // e.g., "Bitcoin", "Ethereum"
  ticker: string;     // e.g., "BTC", "ETH"
  price: number;      // Current price per unit
  quantity: number;   // Amount held
  iconUrl?: string;   // Optional image/icon URL
}

// --- Mock Initial State ---

const initialHoldings: AssetHolding[] = [
  { id: 1, instrument: "Bitcoin", ticker: "BTC", price: 34500.50, quantity: 0.85, iconUrl: 'https://cryptologos.cc/logos/bitcoin-btc-logo.svg?v=025' },
  { id: 2, instrument: "Ethereum", ticker: "ETH", price: 1850.75, quantity: 5.2, iconUrl: 'https://cryptologos.cc/logos/ethereum-eth-logo.svg?v=025' },
  { id: 3, instrument: "Solana", ticker: "SOL", price: 35.12, quantity: 150.0, iconUrl: 'https://cryptologos.cc/logos/solana-sol-logo.svg?v=025' },
  { id: 4, instrument: "USD Coin", ticker: "USDC", price: 1.00, quantity: 500.0, iconUrl: 'https://cryptologos.cc/logos/usd-coin-usdc-logo.svg?v=025' },
];

// --- Utility Functions ---

const formatCurrency = (value: number) => {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(value);
};

const formatQuantity = (value: number, decimals = 4) => {
    return value.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: decimals,
    });
};

const AssetHoldings: FC = () => {
  const [holdings] = useState<AssetHolding[]>(initialHoldings);

  // Calculate total portfolio value
  const portfolioTotal = useMemo(() => {
    return holdings.reduce((sum, asset) => sum + asset.price * asset.quantity, 0);
  }, [holdings]);

  return (
    <Card className="w-full max-w-2xl shadow-lg">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-2xl font-bold">Asset Holdings</CardTitle>
        <div className="text-3xl font-extrabold text-primary flex items-center gap-2">
            <DollarSign className="w-6 h-6 text-muted-foreground"/>
            {formatCurrency(portfolioTotal)}
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[40%]">Instrument</TableHead>
              <TableHead className="text-right">Price</TableHead>
              <TableHead className="text-right">Quantity</TableHead>
              <TableHead className="text-right">Total Value</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {holdings.map((asset) => {
              const totalValue = asset.price * asset.quantity;

              return (
                <TableRow key={asset.id} className="hover:bg-accent/50 transition-colors cursor-pointer">
                  {/* Instrument (Icon + Name/Ticker) */}
                  <TableCell className="font-medium flex items-center gap-3 py-3">
                    <Avatar className="w-8 h-8">
                      <AvatarImage src={asset.iconUrl} alt={asset.ticker} />
                      {/* Fallback uses the first letter of the ticker */}
                      <AvatarFallback className="bg-primary/10 text-primary font-bold text-sm">
                        {asset.ticker.charAt(0)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex flex-col">
                      <span className="font-semibold text-sm">{asset.instrument}</span>
                      <span className="text-xs text-muted-foreground">{asset.ticker}</span>
                    </div>
                  </TableCell>

                  {/* Price */}
                  <TableCell className="text-right text-sm">
                    {formatCurrency(asset.price)}
                  </TableCell>

                  {/* Quantity */}
                  <TableCell className="text-right text-sm text-muted-foreground">
                    {formatQuantity(asset.quantity)}
                  </TableCell>

                  {/* Total Value */}
                  <TableCell className="text-right font-semibold text-sm">
                    {formatCurrency(totalValue)}
                  </TableCell>
                </TableRow>
              );
            })}

            {holdings.length === 0 && (
                <TableRow>
                    <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                        No assets currently held.
                    </TableCell>
                </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};

export default AssetHoldings;