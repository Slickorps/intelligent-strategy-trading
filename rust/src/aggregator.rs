use ndarray::Array2;

/// 蜡烛图 / OHLCV K 线
#[derive(Debug, Clone)]
pub struct Bar {
    pub timestamp: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

/// 原始 Tick 数据
#[derive(Debug, Clone)]
pub struct Tick {
    pub timestamp: i64,
    pub price: f64,
    pub volume: f64,
}

/// 将 tick 数据聚合成指定周期的 OHLCV 蜡烛图
/// `timeframe_ms` 为周期长度（毫秒）
pub fn tick_to_bar(ticks: &[Tick], timeframe_ms: i64) -> Vec<Bar> {
    if ticks.is_empty() {
        return vec![];
    }

    let mut bars: Vec<Bar> = Vec::new();
    let first_ts = ticks[0].timestamp;
    let mut bucket_start = first_ts - (first_ts % timeframe_ms);
    let mut bucket_end = bucket_start + timeframe_ms;

    let mut o: Option<f64> = None;
    let mut h: f64 = f64::NEG_INFINITY;
    let mut l: f64 = f64::INFINITY;
    let mut c: f64 = 0.0;
    let mut v: f64 = 0.0;

    for tick in ticks {
        if tick.timestamp >= bucket_end {
            if let Some(open) = o {
                bars.push(Bar {
                    timestamp: bucket_start,
                    open,
                    high: h,
                    low: l,
                    close: c,
                    volume: v,
                });
            }
            // 前进到下一个桶
            bucket_start = tick.timestamp - (tick.timestamp % timeframe_ms);
            bucket_end = bucket_start + timeframe_ms;
            o = None;
            h = f64::NEG_INFINITY;
            l = f64::INFINITY;
            c = 0.0;
            v = 0.0;
        }

        if o.is_none() {
            o = Some(tick.price);
        }
        if tick.price > h {
            h = tick.price;
        }
        if tick.price < l {
            l = tick.price;
        }
        c = tick.price;
        v += tick.volume;
    }

    // 最后一根 K 线
    if let Some(open) = o {
        bars.push(Bar {
            timestamp: bucket_start,
            open,
            high: h,
            low: l,
            close: c,
            volume: v,
        });
    }

    bars
}

/// 重采样 K 线到更大的周期
/// 将一组 OHLCV K 线从原始周期聚合到目标周期
/// `bars` 必须是等周期、按时间升序排列的
pub fn resample_bars(bars: &[Bar], factor: usize) -> Vec<Bar> {
    if factor <= 1 || bars.is_empty() {
        return bars.to_vec();
    }

    let mut result = Vec::new();
    for chunk in bars.chunks(factor) {
        let open = chunk[0].open;
        let close = chunk[chunk.len() - 1].close;
        let high = chunk
            .iter()
            .map(|b| b.high)
            .fold(f64::NEG_INFINITY, f64::max);
        let low = chunk
            .iter()
            .map(|b| b.low)
            .fold(f64::INFINITY, f64::min);
        let volume: f64 = chunk.iter().map(|b| b.volume).sum();
        result.push(Bar {
            timestamp: chunk[0].timestamp,
            open,
            high,
            low,
            close,
            volume,
        });
    }

    result
}

/// 从 2D 数组（列序: timestamp, open, high, low, close, volume）构造 Bar 切片
pub fn array_to_bars(data: &Array2<f64>) -> Vec<Bar> {
    let n = data.nrows();
    let mut bars = Vec::with_capacity(n);
    for i in 0..n {
        bars.push(Bar {
            timestamp: data[[i, 0]] as i64,
            open: data[[i, 1]],
            high: data[[i, 2]],
            low: data[[i, 3]],
            close: data[[i, 4]],
            volume: data[[i, 5]],
        });
    }
    bars
}