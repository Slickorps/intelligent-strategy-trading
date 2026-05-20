/**
 * P&L chart component — renders equity curve on a <canvas> element.
 */

export class PnLChart {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private data: { time: number; equity: number }[] = [];
  private maxPoints: number = 200;
  private theme = {
    bg: '#131722',
    line: '#2962FF',
    fill: 'rgba(41, 98, 255, 0.12)',
    grid: '#2a2e39',
    text: '#787b86',
  };

  constructor(container: HTMLElement, width?: number, height?: number) {
    this.canvas = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    const logicalW = width ?? container.clientWidth;
    const logicalH = height ?? 280;
    this.canvas.style.width = `${logicalW}px`;
    this.canvas.style.height = `${logicalH}px`;
    this.canvas.width = logicalW * dpr;
    this.canvas.height = logicalH * dpr;

    this.ctx = this.canvas.getContext('2d')!;
    this.ctx.scale(dpr, dpr);
    this.canvas.style.display = 'block';
    container.appendChild(this.canvas);

    this.drawEmpty();
  }

  /** Push a new equity data point (called on each update). */
  push(equity: number, time = Date.now()): void {
    this.data.push({ time, equity });
    if (this.data.length > this.maxPoints) {
      this.data.splice(0, this.data.length - this.maxPoints);
    }
    this.draw();
  }

  /** Replace all data points. */
  setData(points: { time: number; equity: number }[]): void {
    this.data = points.slice(-this.maxPoints);
    this.draw();
  }

  destroy(): void {
    this.canvas.remove();
  }

  // ---------------------------------------------------------------------------
  // Drawing
  // ---------------------------------------------------------------------------
  private drawEmpty(): void {
    const { width, height } = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const w = width / dpr;
    const h = height / dpr;
    const ctx = this.ctx;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = this.theme.bg;
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = this.theme.text;
    ctx.font = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No data yet', w / 2, h / 2);
  }

  private draw(): void {
    const { width, height } = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const w = width / dpr;
    const h = height / dpr;
    const ctx = this.ctx;
    const margin = { top: 20, right: 20, bottom: 30, left: 60 };

    // Background
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = this.theme.bg;
    ctx.fillRect(0, 0, w, h);

    if (this.data.length < 2) {
      ctx.fillStyle = this.theme.text;
      ctx.font = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Waiting for data...', w / 2, h / 2);
      return;
    }

    const values = this.data.map((d) => d.equity);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal || 1;

    const plotW = w - margin.left - margin.right;
    const plotH = h - margin.top - margin.bottom;

    // Grid
    ctx.strokeStyle = this.theme.grid;
    ctx.lineWidth = 1;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
      const y = margin.top + (plotH / gridLines) * i;
      ctx.beginPath();
      ctx.moveTo(margin.left, y);
      ctx.lineTo(w - margin.right, y);
      ctx.stroke();

      // Y labels
      const labelVal = maxVal - (range / gridLines) * i;
      ctx.fillStyle = this.theme.text;
      ctx.font = '11px monospace';
      ctx.textAlign = 'right';
      ctx.fillText(labelVal.toFixed(2), margin.left - 6, y + 4);
    }

    // Equity line
    ctx.beginPath();
    ctx.strokeStyle = this.theme.line;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';

    const xScale = plotW / (this.data.length - 1);
    const yScale = plotH / range;

    this.data.forEach((point, index) => {
      const x = margin.left + index * xScale;
      const y = margin.top + plotH - (point.equity - minVal) * yScale;
      if (index === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();

    // Fill area under line
    const lastIdx = this.data.length - 1;
    ctx.lineTo(margin.left + lastIdx * xScale, margin.top + plotH);
    ctx.lineTo(margin.left, margin.top + plotH);
    ctx.closePath();
    ctx.fillStyle = this.theme.fill;
    ctx.fill();

    // X time labels
    ctx.fillStyle = this.theme.text;
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    const firstTime = new Date(this.data[0].time);
    const lastTime = new Date(this.data[lastIdx].time);
    ctx.fillText(formatTime(firstTime), margin.left, h - margin.bottom + 16);
    ctx.fillText(formatTime(lastTime), w - margin.right, h - margin.bottom + 16);
  }
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}