"use client";

import React, { useRef, useEffect, useState, useCallback } from "react";

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

interface ViewState {
  offsetX: number;
  scale: number;
  isDragging: boolean;
  dragStartX: number;
  dragStartOffsetX: number;
}

const CandlestickChart: React.FC<CandlestickChartProps> = ({ data }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const animationFrameRef = useRef<number>();
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [crosshair, setCrosshair] = useState<{ x: number; y: number } | null>(null);
  
  const [viewState, setViewState] = useState<ViewState>({
    offsetX: 0,
    scale: 1,
    isDragging: false,
    dragStartX: 0,
    dragStartOffsetX: 0,
  });

  // Handle resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const { width, height } = containerRef.current.getBoundingClientRect();
        setDimensions({ width, height });
      }
    };

    updateDimensions();
    window.addEventListener("resize", updateDimensions);
    return () => window.removeEventListener("resize", updateDimensions);
  }, []);

  // Calculate price range
  const priceRange = React.useMemo(() => {
    if (!data || data.length === 0) {
      return { min: 0, max: 1, range: 1 };
    }
    const prices = data.flatMap(d => [d.high, d.low]);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const padding = (max - min) * 0.1;
    return { min: min - padding, max: max + padding, range: max - min + 2 * padding };
  }, [data]);

  // Drawing function
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || dimensions.width === 0 || !data || data.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { width, height } = dimensions;
    const dpr = window.devicePixelRatio || 1;

    // Set canvas size
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Calculate visible range
    const candleWidth = Math.max(4, Math.min(16, (width * 0.6) / data.length)) * viewState.scale;
    const candleSpacing = candleWidth * 1.5;
    const totalWidth = data.length * candleSpacing;
    const startIndex = Math.max(0, Math.floor(-viewState.offsetX / candleSpacing));
    const endIndex = Math.min(data.length, Math.ceil((width - viewState.offsetX) / candleSpacing) + 1);

    // Draw grid lines
    ctx.strokeStyle = "rgba(128, 145, 160, 0.08)";
    ctx.lineWidth = 1;
    const gridLines = 8;
    for (let i = 0; i <= gridLines; i++) {
      const y = (height / gridLines) * i;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Draw price labels
    ctx.fillStyle = "rgba(183, 190, 200, 0.6)";
    ctx.font = "9px 'SF Mono', monospace";
    ctx.textAlign = "right";
    for (let i = 0; i <= gridLines; i++) {
      const priceValue = priceRange.max - (priceRange.range / gridLines) * i;
      const y = (height / gridLines) * i;
      ctx.fillText(priceValue.toFixed(5), width - 8, y + 3);
    }

    // Draw candlesticks with animation
    for (let i = startIndex; i < endIndex; i++) {
      const bar = data[i];
      const x = viewState.offsetX + i * candleSpacing + candleSpacing / 2;

      if (x < -candleWidth || x > width + candleWidth) continue;

      const isUp = bar.close >= bar.open;
      const isHovered = hoveredIndex === i;

      // Colors - Green for up, Red for down (better visibility)
      const upColor = isHovered ? "rgba(34, 211, 238, 1)" : "rgba(99, 230, 161, 0.9)";
      const downColor = isHovered ? "rgba(251, 113, 133, 1)" : "rgba(239, 68, 68, 0.9)";
      const color = isUp ? upColor : downColor;

      // Calculate Y positions
      const highY = ((priceRange.max - bar.high) / priceRange.range) * height;
      const lowY = ((priceRange.max - bar.low) / priceRange.range) * height;
      const openY = ((priceRange.max - bar.open) / priceRange.range) * height;
      const closeY = ((priceRange.max - bar.close) / priceRange.range) * height;
      const bodyTop = Math.min(openY, closeY);
      const bodyBottom = Math.max(openY, closeY);
      const bodyHeight = Math.max(1, bodyBottom - bodyTop);

      // Draw wick with glow effect for hovered
      if (isHovered) {
        ctx.shadowColor = color;
        ctx.shadowBlur = 8;
      }
      
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(1, candleWidth / 5);
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Draw body with gradient
      if (isUp) {
        // Hollow/outline for up candles
        ctx.strokeStyle = color;
        ctx.lineWidth = isHovered ? 2 : 1.5;
        ctx.strokeRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
        
        // Subtle fill
        ctx.fillStyle = isHovered ? "rgba(99, 230, 161, 0.2)" : "rgba(99, 230, 161, 0.1)";
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
      } else {
        // Filled for down candles
        ctx.fillStyle = color;
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
      }

      ctx.shadowBlur = 0;
    }

    // Draw crosshair
    if (crosshair && !viewState.isDragging) {
      ctx.strokeStyle = "rgba(125, 211, 252, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      
      // Vertical line
      ctx.beginPath();
      ctx.moveTo(crosshair.x, 0);
      ctx.lineTo(crosshair.x, height);
      ctx.stroke();
      
      // Horizontal line
      ctx.beginPath();
      ctx.moveTo(0, crosshair.y);
      ctx.lineTo(width, crosshair.y);
      ctx.stroke();
      
      ctx.setLineDash([]);

      // Price label at crosshair
      const price = priceRange.max - (crosshair.y / height) * priceRange.range;
      ctx.fillStyle = "rgba(125, 211, 252, 0.9)";
      ctx.fillRect(width - 70, crosshair.y - 10, 65, 18);
      ctx.fillStyle = "rgba(7, 9, 12, 1)";
      ctx.font = "10px 'SF Mono', monospace";
      ctx.textAlign = "right";
      ctx.fillText(price.toFixed(5), width - 8, crosshair.y + 3);
    }

  }, [data, dimensions, viewState, hoveredIndex, crosshair, priceRange]);

  // Animation loop
  useEffect(() => {
    const animate = () => {
      draw();
      animationFrameRef.current = requestAnimationFrame(animate);
    };
    animate();
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [draw]);

  // Mouse handlers
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!canvasRef.current || !data || data.length === 0) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setCrosshair({ x, y });

    if (viewState.isDragging) {
      const deltaX = e.clientX - viewState.dragStartX;
      setViewState(prev => ({
        ...prev,
        offsetX: prev.dragStartOffsetX + deltaX,
      }));
      return;
    }

    // Find hovered candle
    const candleWidth = Math.max(4, Math.min(16, (dimensions.width * 0.6) / data.length)) * viewState.scale;
    const candleSpacing = candleWidth * 1.5;
    const index = Math.floor((x - viewState.offsetX) / candleSpacing);
    
    if (index >= 0 && index < data.length) {
      setHoveredIndex(index);
    } else {
      setHoveredIndex(null);
    }
  }, [data, dimensions, viewState]);

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    setViewState(prev => ({
      ...prev,
      isDragging: true,
      dragStartX: e.clientX,
      dragStartOffsetX: prev.offsetX,
    }));
  }, []);

  const handleMouseUp = useCallback(() => {
    setViewState(prev => ({ ...prev, isDragging: false }));
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHoveredIndex(null);
    setCrosshair(null);
    setViewState(prev => ({ ...prev, isDragging: false }));
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const delta = e.deltaY * -0.001;
    const newScale = Math.max(0.5, Math.min(5, viewState.scale + delta));
    
    setViewState(prev => ({
      ...prev,
      scale: newScale,
    }));
  }, [viewState.scale]);

  // Reset zoom button handler
  const handleResetZoom = useCallback(() => {
    setViewState({
      offsetX: 0,
      scale: 1,
      isDragging: false,
      dragStartX: 0,
      dragStartOffsetX: 0,
    });
  }, []);

  // Handle empty data - after all hooks
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

  return (
    <div 
      ref={containerRef} 
      style={{ 
        width: "100%", 
        height: "100%", 
        position: "relative",
        userSelect: "none",
      }}
    >
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onWheel={handleWheel}
        style={{
          width: "100%",
          height: "100%",
          cursor: viewState.isDragging ? "grabbing" : "crosshair",
        }}
      />
      
      {/* Tooltip */}
      {hoveredIndex !== null && data[hoveredIndex] && crosshair && !viewState.isDragging && (
        <div
          style={{
            position: "absolute",
            left: Math.min(crosshair.x + 15, dimensions.width - 165),
            top: Math.min(crosshair.y + 15, dimensions.height - 95),
            background: "rgba(15, 19, 24, 0.96)",
            border: "1px solid rgba(125, 211, 252, 0.3)",
            borderRadius: "10px",
            padding: "10px 12px",
            fontSize: "10px",
            color: "#fff",
            pointerEvents: "none",
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
            zIndex: 10,
            animation: "fadeIn 0.15s ease-out",
          }}
        >
          <div style={{ marginBottom: "8px", fontSize: "9px", opacity: 0.7, fontWeight: 600 }}>
            {data[hoveredIndex].label}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "5px 10px" }}>
            <span style={{ opacity: 0.6 }}>O:</span>
            <span style={{ fontFamily: "monospace", fontWeight: 500 }}>
              {data[hoveredIndex].open.toFixed(5)}
            </span>
            <span style={{ opacity: 0.6 }}>H:</span>
            <span style={{ fontFamily: "monospace", fontWeight: 500, color: "rgba(99, 230, 161, 1)" }}>
              {data[hoveredIndex].high.toFixed(5)}
            </span>
            <span style={{ opacity: 0.6 }}>L:</span>
            <span style={{ fontFamily: "monospace", fontWeight: 500, color: "rgba(239, 68, 68, 1)" }}>
              {data[hoveredIndex].low.toFixed(5)}
            </span>
            <span style={{ opacity: 0.6 }}>C:</span>
            <span style={{ 
              fontFamily: "monospace", 
              fontWeight: 600,
              color: data[hoveredIndex].close >= data[hoveredIndex].open ? "rgba(99, 230, 161, 1)" : "rgba(239, 68, 68, 1)"
            }}>
              {data[hoveredIndex].close.toFixed(5)}
            </span>
          </div>
        </div>
      )}

      {/* Controls */}
      <div style={{
        position: "absolute",
        top: "10px",
        right: "10px",
        display: "flex",
        gap: "6px",
        zIndex: 5,
      }}>
        <button
          onClick={handleResetZoom}
          style={{
            padding: "6px 10px",
            background: "rgba(15, 19, 24, 0.8)",
            border: "1px solid rgba(125, 211, 252, 0.2)",
            borderRadius: "8px",
            color: "var(--accent)",
            fontSize: "9px",
            fontWeight: 600,
            cursor: "pointer",
            transition: "all 0.2s ease",
            backdropFilter: "blur(8px)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(125, 211, 252, 0.15)";
            e.currentTarget.style.borderColor = "rgba(125, 211, 252, 0.4)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(15, 19, 24, 0.8)";
            e.currentTarget.style.borderColor = "rgba(125, 211, 252, 0.2)";
          }}
        >
          Reset Zoom
        </button>
        <div style={{
          padding: "6px 10px",
          background: "rgba(15, 19, 24, 0.8)",
          border: "1px solid rgba(128, 145, 160, 0.2)",
          borderRadius: "8px",
          color: "var(--text-3)",
          fontSize: "9px",
          fontWeight: 600,
          backdropFilter: "blur(8px)",
        }}>
          {(viewState.scale * 100).toFixed(0)}%
        </div>
      </div>

      {/* Instructions */}
      <div style={{
        position: "absolute",
        bottom: "10px",
        left: "10px",
        padding: "6px 10px",
        background: "rgba(15, 19, 24, 0.7)",
        border: "1px solid rgba(128, 145, 160, 0.15)",
        borderRadius: "8px",
        color: "var(--text-3)",
        fontSize: "8px",
        backdropFilter: "blur(8px)",
        zIndex: 5,
      }}>
        Scroll to zoom • Drag to pan
      </div>
    </div>
  );
};

export default CandlestickChart;
