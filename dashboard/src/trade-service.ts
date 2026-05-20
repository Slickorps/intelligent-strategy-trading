/**
 * Core trade service — WebSocket connection & state management
 * for the Intelligent Strategy Trading dashboard.
 */

export interface Position {
  symbol: string;
  side: 'long' | 'short';
  size: number;
  entryPrice: number;
  currentPrice: number;
  unrealizedPnl: number;
  pnlPct: number;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  type: 'market' | 'limit' | 'stop';
  price?: number;
  size: number;
  status: 'pending' | 'filled' | 'rejected' | 'cancelled';
  createdAt: string;
}

export interface AccountSummary {
  balance: number;
  equity: number;
  margin: number;
  freeMargin: number;
  marginLevel: number;
  dailyPnl: number;
  totalPnl: number;
}

export interface DashboardState {
  account: AccountSummary | null;
  positions: Position[];
  orders: Order[];
  connected: boolean;
  lastUpdate: string | null;
}

type StateListener = (state: DashboardState) => void;

const DEFAULT_ACCOUNT: AccountSummary = {
  balance: 0,
  equity: 0,
  margin: 0,
  freeMargin: 0,
  marginLevel: 0,
  dailyPnl: 0,
  totalPnl: 0,
};

export class TradeService {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Set<StateListener> = new Set();
  private pingTimer: ReturnType<typeof setInterval> | null = null;

  state: DashboardState = {
    account: null,
    positions: [],
    orders: [],
    connected: false,
    lastUpdate: null,
  };

  constructor(private url: string = 'ws://localhost:8000/ws') {}

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    this.createSocket();
  }

  disconnect(): void {
    this.clearTimers();
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }
    this.updateState({ connected: false });
  }

  subscribe(listener: StateListener): () => void {
    this.listeners.add(listener);
    // Immediately push current state
    listener({ ...this.state });
    return () => this.listeners.delete(listener);
  }

  // ---------------------------------------------------------------------------
  // Internal
  // ---------------------------------------------------------------------------
  private createSocket(): void {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.updateState({ connected: true });
      this.startPing();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);
        this.handleMessage(payload);
      } catch {
        // non-JSON message – ignore
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      this.updateState({ connected: false });
      this.clearTimers();
      if (event.code !== 1000) {
        // Abnormal close → auto-reconnect after 3 s
        this.reconnectTimer = setTimeout(() => this.createSocket(), 3_000);
      }
    };

    this.ws.onerror = () => {
      // onclose will fire afterwards
    };
  }

  private handleMessage(payload: Record<string, unknown>): void {
    const { type, data } = payload as { type?: string; data?: Record<string, unknown> };
    if (!type) return;

    const patch: Partial<DashboardState> = { lastUpdate: new Date().toISOString() };

    switch (type) {
      case 'account':
        patch.account = { ...DEFAULT_ACCOUNT, ...(data ?? {}) } as AccountSummary;
        break;
      case 'positions':
        patch.positions = (data as unknown as Position[]) ?? [];
        break;
      case 'orders':
        patch.orders = (data as unknown as Order[]) ?? [];
        break;
      case 'full_state':
        patch.account = { ...DEFAULT_ACCOUNT, ...((data as any)?.account ?? {}) } as AccountSummary;
        patch.positions = ((data as any)?.positions ?? []) as Position[];
        patch.orders = ((data as any)?.orders ?? []) as Order[];
        break;
      default:
        return; // unknown type, skip
    }

    this.updateState(patch);
  }

  private updateState(patch: Partial<DashboardState>): void {
    this.state = { ...this.state, ...patch };
    const snapshot = { ...this.state };
    for (const listener of this.listeners) {
      try {
        listener(snapshot);
      } catch {
        // swallow listener errors
      }
    }
  }

  private startPing(): void {
    this.pingTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30_000);
  }

  private clearTimers(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}