"use client";

import React from "react";
import { ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip } from "recharts";

interface CandlestickBar {
  i: number;
  open: number;
  high: number;
  low: number;
  close: number;
  label: string;
}

interface CandlestickChartProps {
  data: CandlestickBar[];
}

const CandlestickChart: React.FC<CandlestickChartProps> = ({ data }) => {
  const [hoveredIndex, setHoveredIndex] = React.useState<number | null>(null);

  // Handle empty data
  if (!data || data.length === 0) {
    return (
      <div style={{ 
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center", 
        height: "100%",
        color: "var(--text-3)",
        fontSize: "10px"
      }}>
        No data available
      </div>
    );
  }

  // Calculate min/max for Y-axis domain
  const yMin = Math.min(...data.map(d => d.low));
  const yMax = Math.max(...data.map(d => d.high));
  const padding = (yMax - yMin) * 0.1;

  // Calculate candle width based on number of data points
  const candleWidth = Math.max(2, Math.min(8, 300 / data.length));
  const wickWidth = Math.max(1, candleWidth / 4);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <svg
        width="100%"
        height="100%"
        style={{ cursor: "crosshair" }}
        onMouseLeave={() => setHoveredIndex(null)}
      >
        <defs>
          <linearGradient id="gridGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(128,145,160,0.12)" />
            <stop offset="100%" stopColor="rgba(128,145,160,0.04)" />
          </linearGradient>
        </defs>
        
        {/* CartesianGrid background */}
        <rect width="100%" height="100%" fill="transparent" />
        
        {/* Render candlesticks */}
        <g transform="translate(0, 8)">
          {data.map((bar, index) => {
            const x = (index / (data.length - 1 || 1)) * 100; // percentage
            const isUp = bar.close >= bar.open;
            const color = isUp ? "#000000" : "#0066ff";
            const bodyTop = isUp ? bar.close : bar.open;
            const bodyBottom = isUp ? bar.open : bar.close;
            
            // Convert prices to percentages for positioning
            const highY = ((yMax + padding - bar.high) / (yMax - yMin + 2 * padding)) * 100;
            const lowY = ((yMax + padding - bar.low) / (yMax - yMin + 2 * padding)) * 100;
            const bodyTopY = ((yMax + padding - bodyTop) / (yMax - yMin + 2 * padding)) * 100;
            const bodyBottomY = ((yMax + padding - bodyBottom) / (yMax - yMin + 2 * padding)) * 100;
            const bodyHeight = Math.max(0.5, bodyBottomY - bodyTopY);

            return (
              <g
                key={bar.i}
                onMouseEnter={() => setHoveredIndex(index)}
                style={{ cursor: "pointer" }}
              >
                {/* Wick (high-low) */}
                <line
                  x1={`${x}%`}
                  y1={`${highY}%`}
                  x2={`${x}%`}
                  y2={`${lowY}%`}
                  stroke={color}
                  strokeWidth={wickWidth}
                  opacity={hoveredIndex === index ? 1 : 0.85}
                />
                
                {/* Body (open-close) */}
                <rect
                  x={`calc(${x}% - ${candleWidth / 2}px)`}
                  y={`${bodyTopY}%`}
                  width={candleWidth}
                  height={`${bodyHeight}%`}
                  fill={color}
                  opacity={hoveredIndex === index ? 1 : 0.85}
                />
                
                {/* Invisible hover target for better UX */}
                <rect
                  x={`calc(${x}% - ${Math.max(candleWidth, 10)}px)`}
                  y="0"
                  width={Math.max(candleWidth * 2, 20)}
                  height="100%"
                  fill="transparent"
                />
              </g>
            );
          })}
        </g>

        {/* Custom tooltip */}
        {hoveredIndex !== null && data[hoveredIndex] && (
          <foreignObject
            x="10"
            y="10"
            width="160"
            height="80"
            style={{ pointerEvents: "none" }}
          >
            <div
              style={{
                background: "rgba(15,19,24,.94)",
                border: "1px solid rgba(255,255,255,.1)",
                borderRadius: "10px",
                padding: "10px 12px",
                fontSize: "10px",
                color: "#fff",
                fontFamily: "inherit",
              }}
            >
              <div style={{ marginBottom: "6px", fontSize: "9px", opacity: 0.6 }}>
                {data[hoveredIndex].label}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 8px" }}>
                <span style={{ opacity: 0.7 }}>O:</span>
                <span style={{ fontFamily: "monospace" }}>
                  {data[hoveredIndex].open.toFixed(5)}
                </span>
                <span style={{ opacity: 0.7 }}>H:</span>
                <span style={{ fontFamily: "monospace" }}>
                  {data[hoveredIndex].high.toFixed(5)}
                </span>
                <span style={{ opacity: 0.7 }}>L:</span>
                <span style={{ fontFamily: "monospace" }}>
                  {data[hoveredIndex].low.toFixed(5)}
                </span>
                <span style={{ opacity: 0.7 }}>C:</span>
                <span style={{ fontFamily: "monospace" }}>
                  {data[hoveredIndex].close.toFixed(5)}
                </span>
              </div>
            </div>
          </foreignObject>
        )}
      </svg>
    </ResponsiveContainer>
  );
};

export default CandlestickChart;
