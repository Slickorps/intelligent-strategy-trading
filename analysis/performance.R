#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# performance.R — Backtest Performance Analytics for IST Platform
#
# Usage:
#   Rscript analysis/performance.R --file=data/EURUSD_1h.csv --benchmark=0.05
#
# Computes: Sharpe, Sortino, Calmar ratios, max drawdown periods,
# VaR / CVaR, rolling Sharpe, and draws the full tear sheet chart.
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(optparse)
  library(ggplot2)
  library(data.table)
  library(gridExtra)
  library(zoo)
})

# ---- CLI ----
option_list <- list(
  make_option("--file",      type = "character", default = "data/EURUSD_1h.csv",
              help = "Path to OHLCV CSV [default %default]"),
  make_option("--benchmark", type = "numeric",   default = 0.05,
              help = "Risk-free rate (annual) [default %default]"),
  make_option("--plot",      type = "character", default = "performance_tearsheet.png",
              help = "Output plot path [default %default]")
)
parser <- OptionParser(option_list = option_list,
                       description = "Backtest performance analytics for IST Platform")
args   <- parse_args(parser)

# ---- Load Data ----
cat(sprintf("[INFO] Loading data from %s ...\n", args$file))
if (!file.exists(args$file)) stop(sprintf("File not found: %s", args$file))

dt <- fread(args$file)
setnames(dt, tolower(names(dt)))

# Calculate log returns
dt[, ret := log(close / shift(close, 1))]
dt <- na.omit(dt)

ret_vec <- dt$ret
n       <- length(ret_vec)
rf_daily <- log(1 + args$benchmark) / 252

cat(sprintf("[INFO] %d return observations loaded\n", n))

# ---- Core Metrics ----
total_ret    <- cumsum(ret_vec)
total_simple <- exp(tail(total_ret, 1)) - 1
ann_ret      <- mean(ret_vec) * 252
ann_vol      <- sd(ret_vec) * sqrt(252)
sharpe       <- (ann_ret - args$benchmark) / ann_vol

# Sortino ratio
downside     <- pmax(0, -(ret_vec - rf_daily))
downside_sd  <- sqrt(mean(downside ^ 2)) * sqrt(252)
sortino      <- (ann_ret - args$benchmark) / downside_sd

# Max drawdown
cum_eq <- exp(cumsum(ret_vec))
dd     <- cum_eq / cummax(cum_eq) - 1
max_dd <- min(dd)

# Calmar
calmar <- ann_ret / abs(max_dd)

# VaR / CVaR
var_95  <- quantile(ret_vec, 0.05)
cvar_95 <- mean(ret_vec[ret_vec <= var_95])

# Win rate / Profit factor
wins   <- sum(ret_vec > 0)
losses <- sum(ret_vec < 0)
win_rate <- wins / (wins + losses)

gross_profit  <- sum(ret_vec[ret_vec > 0])
gross_loss    <- abs(sum(ret_vec[ret_vec < 0]))
profit_factor <- ifelse(gross_loss == 0, Inf, gross_profit / gross_loss)

# ---- Print Results ----
cat("\n========== PERFORMANCE REPORT ==========\n")
cat(sprintf("Total Return:          %+.2f%%\n",   total_simple * 100))
cat(sprintf("Annualized Return:     %+.2f%%\n",   ann_ret * 100))
cat(sprintf("Annualized Volatility:  %.2f%%\n",   ann_vol * 100))
cat(sprintf("Sharpe Ratio:           %.3f\n",     sharpe))
cat(sprintf("Sortino Ratio:          %.3f\n",     sortino))
cat(sprintf("Calmar Ratio:           %.3f\n",     calmar))
cat(sprintf("Max Drawdown:          %+.2f%%\n",   max_dd * 100))
cat(sprintf("VaR 95%% (daily):      %+.4f%%\n",  var_95 * 100))
cat(sprintf("CVaR 95%% (daily):     %+.4f%%\n",  cvar_95 * 100))
cat(sprintf("Win Rate:               %.1f%%\n",   win_rate * 100))
cat(sprintf("Profit Factor:           %.3f\n",     profit_factor))
cat(sprintf("N obs:                   %d\n",      n))
cat("==========================================\n")

# ---- Rolling Metrics ----
window <- min(252, n %/% 2)
cat(sprintf("[INFO] Computing rolling metrics (window=%d)...\n", window))

rolling_sharpe <- rollapply(ret_vec, width = window, FUN = function(x) {
  r <- mean(x) * 252
  v <- sd(x) * sqrt(252)
  (r - args$benchmark) / v
}, by.column = FALSE, fill = NA)

rolling_vol <- rollapply(ret_vec, width = window, FUN = function(x) {
  sd(x) * sqrt(252)
}, by.column = FALSE, fill = NA)

# ---- Plot Tear Sheet ----
plot_df <- data.table(
  idx            = seq_len(n),
  equity         = cum_eq,
  dd             = dd,
  ret            = ret_vec,
  rolling_sharpe = rolling_sharpe,
  rolling_vol    = rolling_vol
)

# Equity curve + drawdown
p1 <- ggplot(plot_df, aes(x = idx)) +
  geom_line(aes(y = equity), color = "#3498DB", linewidth = 0.6) +
  labs(x = "", y = "Equity Curve") +
  theme_minimal(base_size = 11)

p2 <- ggplot(plot_df, aes(x = idx)) +
  geom_ribbon(aes(ymin = 0, ymax = dd), fill = "#E74C3C", alpha = 0.3) +
  geom_line(aes(y = dd), color = "#E74C3C", linewidth = 0.5) +
  labs(x = "", y = "Drawdown") +
  scale_y_continuous(labels = scales::percent) +
  theme_minimal(base_size = 11)

# Return density + VaR
p3 <- ggplot(plot_df, aes(x = ret)) +
  geom_histogram(aes(y = after_stat(density)), bins = 60,
                 fill = "#34495E", alpha = 0.7) +
  geom_vline(xintercept = var_95, color = "#E74C3C", linetype = "dashed",
             linewidth = 0.8) +
  annotate("text", x = var_95 * 1.1, y = 0.5, label = "VaR 95%",
           color = "#E74C3C", hjust = 0, size = 3.5) +
  labs(x = "Daily Log Return", y = "Density") +
  theme_minimal(base_size = 11)

# Rolling Sharpe
p4 <- ggplot(plot_df[!is.na(rolling_sharpe)], aes(x = idx, y = rolling_sharpe)) +
  geom_line(color = "#2ECC71", linewidth = 0.6) +
  geom_hline(yintercept = 0, linetype = "dotted", color = "gray50") +
  labs(x = "Observation", y = "Rolling Sharpe") +
  theme_minimal(base_size = 11)

# Assemble tear sheet
png(args$plot, width = 1600, height = 1000, res = 150)
grid.arrange(p1, p2, p3, p4,
             ncol = 2, nrow = 2,
             top = "IST Performance Tear Sheet")
dev.off()

cat(sprintf("[INFO] Tear sheet saved to %s\n", args$plot))
cat("[DONE] Performance analysis complete.\n")