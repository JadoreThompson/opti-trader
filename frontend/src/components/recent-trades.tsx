import { type FC, useState } from "react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils"; // Assuming `cn` utility is available

// --- Types Definition ---

type TradeSide = "buy" | "sell";

interface Trade {
  id: number;
  time: Date;
  price: number;
  quantity: number;
  side: TradeSide;
}

// --- Utility Functions ---

const formatPrice = (price: number) => {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
};

const formatQuantity = (quantity: number) => {
  return quantity.toLocaleString("en-US", { maximumFractionDigits: 4 });
};

const formatTime = (date: Date) => {
  return date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false, // Use 24-hour format (HH:MM:SS)
  });
};

// --- Mock Initial State ---

const generateMockTrades = (count: number): Trade[] => {
  const trades: Trade[] = [];
  let basePrice = 30500.00;
  
  for (let i = 0; i < count; i++) {
    const time = new Date(Date.now() - (count - i) * 1500); // Backdate trades slightly
    const side: TradeSide = Math.random() > 0.5 ? "buy" : "sell";
    const quantity = Math.random() * 0.5 + 0.05; // 0.05 to 0.55 volume
    
    // Slight price fluctuation based on side
    const priceChange = (Math.random() * 0.5) * (side === "buy" ? 1 : -1);
    basePrice += priceChange;

    trades.push({
      id: i + 1,
      time: time,
      price: basePrice,
      quantity: quantity,
      side: side,
    });
  }
  return trades.reverse(); // Newest first
};

const initialTrades: Trade[] = generateMockTrades(30);

// --- Main Component: RecentTrades ---

const RecentTrades: FC = () => {
  const [trades] = useState<Trade[]>(initialTrades);

  return (
    <Card className="w-full max-w-sm shadow-xl border">
      <CardHeader>
        <CardTitle className="text-xl">Recent Trades (BTC/USD)</CardTitle>
      </CardHeader>
      
      <CardContent className="p-0">
        <ScrollArea className="h-[450px]">
          <Table>
            <TableHeader className="sticky top-0 bg-background/95 backdrop-blur-sm z-10">
              <TableRow>
                <TableHead className="w-[35%] pl-4">Time</TableHead>
                <TableHead className="w-[35%] text-right">Price</TableHead>
                <TableHead className="w-[30%] text-right pr-4">Quantity</TableHead>
              </TableRow>
            </TableHeader>
            
            <TableBody>
              {trades.map((trade) => {
                const isBuy = trade.side === "buy";
                const quantityColor = isBuy
                  ? "text-green-500 font-medium"
                  : "text-red-500 font-medium";

                return (
                  <TableRow 
                    key={trade.id} 
                    className={cn(
                        "text-xs transition-colors",
                        // Subtle background hover indicating the trade side
                        isBuy ? "hover:bg-green-500/10" : "hover:bg-red-500/10"
                    )}
                  >
                    {/* Time */}
                    <TableCell className="py-1.5 pl-4 text-muted-foreground">
                      {formatTime(trade.time)}
                    </TableCell>

                    {/* Price */}
                    <TableCell className="py-1.5 text-right font-mono">
                      {formatPrice(trade.price)}
                    </TableCell>

                    {/* Quantity (Color Coded) */}
                    <TableCell className={cn("py-1.5 text-right pr-4", quantityColor)}>
                      {formatQuantity(trade.quantity)}
                    </TableCell>
                  </TableRow>
                );
              })}
              
              {trades.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} className="h-24 text-center text-muted-foreground">
                    No recent trades recorded.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  );
};

export default RecentTrades;