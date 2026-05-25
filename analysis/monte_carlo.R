#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# monte_carlo.R — Monte Carlo Path Simulation for IST Platform
#
# Usage:
#   Rscript analysis/monte_carlo.R --runs=10000 --horizon=252 --file=data/EURUSD_1h.csv
#
# Generates synthetic equity curves through geometric Brownian motion
# and computes P5 / P50 / P95 terminal wealth bands.
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(optparse)
  library(ggplot2)
  library(data.table)
})

# ---- CLI ----
option_list <- list(
  make_option("--file",   type = "character", default = "data/EURUSD_1h.csv",
              help = "Path to OHLCV CSV [default %default]"),
  make_option("--runs",   type = "integer",   default = 10000,
              help = "Number of simulation paths [default %default]"),
  make_option("--horizon",type = "integer",   default = 252,
              help = "Trading days to simulate [default %default]"),
  make_option("--capital",type = "numeric",   default = 100000,
              help = "Initial capital [default %default]"),
  make_option("--plot",   type = "character", default = "monte_carlo_paths.png",
              help = "Output plot path [default %default]"),
  make_option("--csv",    type = "character", default = NULL,
              help = "Output CSV path for results [default NULL]")
)
parser <- OptionParser(option_list = option_list,
                       description = "Monte Carlo path simulator for IST Platform")
args   <- parse_args(parser)

# ---- Load Returns ----
cat(sprintf("[INFO] Loading data from %s ...\n", args$file))
if (!file.exists(args$file)) {
  stop(sprintf("File not found: %s", args$file))
}

dt <- fread(args$file)
setnames(dt, tolower(names(dt)))
dt[, ret := log(close / shift(close, 1))]
dt <- na.omit(dt)

daily_ret <- dt[, mean(ret)]     # mean log return per bar
daily_vol <- dt[, sd(ret)]       # volatility per bar

cat(sprintf("[INFO] Mean log ret: %.6f, Vol: %.6f\n", daily_ret, daily_vol))

# ---- Simulation ----
set.seed(42)
runs    <- args$runs
horizon <- args$horizon

# Pre-allocate matrix: runs rows x (horizon+1) columns
paths <- matrix(NA_real_, nrow = runs, ncol = horizon + 1)
paths[, 1] <- args$capital

cat(sprintf("[INFO] Running %d Monte Carlo paths (%d steps each) ...\n", runs, horizon))
pb <- txtProgressBar(min = 0, max = runs, style = 3)

for (i in seq_len(runs)) {
  z <- rnorm(horizon, mean = daily_ret, sd = daily_vol)
  cum_ret <- cumsum(z)
  paths[i, -1] <- args$capital * exp(cum_ret)
  setTxtProgressBar(pb, i)
}
close(pb)

# ---- Percentile Analysis ----
terminal <- paths[, ncol(paths)]

quantiles <- quantile(terminal, probs = c(0.05, 0.25, 0.50, 0.75, 0.95))
cat("\n=== Terminal Wealth Percentiles ===\n")
print(round(quantiles, 2))

p5_path  <- paths[which.min(abs(terminal - quantiles["5%"])), ]
p50_path <- paths[which.min(abs(terminal - quantiles["50%"])), ]
p95_path <- paths[which.min(abs(terminal - quantiles["95%"])), ]

cat(sprintf("Probability of loss:     %.1f%%\n",
            100 * mean(terminal < args$capital)))
cat(sprintf("Probability of >20%% gain: %.1f%%\n",
            100 * mean(terminal > args$capital * 1.20)))

# ---- Plot ----
df <- data.table(
  step = rep(0:horizon, 3),
  value = c(p5_path, p50_path, p95_path),
  band  = rep(c("P5", "P50", "P95"), each = horizon + 1)
)

p <- ggplot(df, aes(x = step, y = value, color = band)) +
  geom_line(linewidth = 1) +
  scale_color_manual(values = c("P5" = "#E74C3C", "P50" = "#3498DB", "P95" = "#2ECC71")) +
  labs(
    title    = "Monte Carlo Equity Path Simulation",
    subtitle = sprintf("%s runs, %d-day horizon | P5/P50/P95 bands", scales::comma(runs), horizon),
    x        = "Trading Day",
    y        = "Portfolio Value",
    color    = "Percentile"
  ) +
  theme_minimal(base_size = 14) +
  theme(plot.title = element_text(face = "bold"))

ggsave(args$plot, p, width = 10, height = 6, dpi = 150)
cat(sprintf("[INFO] Plot saved to %s\n", args$plot))

# ---- Optional CSV Export ----
if (!is.null(args$csv)) {
  fwrite(data.table(run = seq_len(runs), terminal = terminal), args$csv)
  cat(sprintf("[INFO] Results saved to %s\n", args$csv))
}

cat("[DONE] Monte Carlo simulation complete.\n")