#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# market_regime.R — Market Regime Detection via HMM & Volatility Clustering
#
# Usage:
#   Rscript analysis/market_regime.R \
#     --file=data/EURUSD_1h.csv \
#     --states=3 \
#     --method=hmm \
#     --plot=market_regime.png
#
#   Rscript analysis/market_regime.R \
#     --file=data/EURUSD_1h.csv \
#     --method=volatility \
#     --window=20 \
#     --plot=vol_regime.png
#
# Methods: hmm (Hidden Markov Model) | volatility (clustering)
# HMM states: typically 3 = bull/range/bear
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(optparse)
  library(ggplot2)
  library(data.table)
  library(gridExtra)
  library(scales)
  library(zoo)
})

# ---- CLI ----
option_list <- list(
  make_option("--file",    type = "character", default = "data/EURUSD_1h.csv",
              help = "Path to OHLCV CSV [default %default]"),
  make_option("--method",  type = "character", default = "hmm",
              help = "Detection method: hmm | volatility [default %default]"),
  make_option("--states",  type = "integer",   default = 3,
              help = "Number of HMM hidden states [default %default]"),
  make_option("--window",  type = "integer",   default = 20,
              help = "Rolling window for volatility clustering [default %default]"),
  make_option("--plot",    type = "character", default = "market_regime.png",
              help = "Output plot path [default %default]")
)
parser <- OptionParser(option_list = option_list,
                       description = "Market regime detection for IST Platform")
args <- parse_args(parser)

# ---- Load Data ----
cat(sprintf("[INFO] Loading data from %s ...\n", args$file))
if (!file.exists(args$file)) stop(sprintf("File not found: %s", args$file))

dt <- fread(args$file)
setnames(dt, tolower(names(dt)))

# Ensure required columns
required_cols <- c("close")
missing_cols <- setdiff(required_cols, names(dt))
if (length(missing_cols) > 0) {
  stop(sprintf("Missing columns: %s", paste(missing_cols, collapse = ", ")))
}

has_ohlc <- all(c("open", "high", "low", "close") %in% names(dt))

# Calculate returns & features
dt[, ret := log(close / shift(close, 1))]
dt <- na.omit(dt)
n <- nrow(dt)

cat(sprintf("[INFO] %d observations loaded\n", n))

ret_vec <- dt$ret

# ---- Feature Engineering ----
# Rolling volatility
dt[, vol_5 := rollapply(ret, width = 5,  FUN = sd, fill = NA, align = "right")]
dt[, vol_20 := rollapply(ret, width = 20, FUN = sd, fill = NA, align = "right")]

# Rolling mean return (trend strength)
dt[, ret_ma_10 := rollapply(ret, width = 10, FUN = mean, fill = NA, align = "right")]

if (has_ohlc) {
  # Parkinson volatility (uses high-low range)
  dt[, parkinson := sqrt(1 / (4 * log(2)) * (log(high / low)) ^ 2)]
  
  # Garman-Klass volatility
  dt[, gk_vol := sqrt(0.5 * (log(high / low)) ^ 2 -
                       (2 * log(2) - 1) * (log(close / open)) ^ 2)]
  
  # Average true range
  dt[, tr := pmax(high - low,
                  abs(high - shift(close, 1)),
                  abs(low  - shift(close, 1)),
                  na.rm = TRUE)]
  dt[, atr_14 := rollapply(tr, width = 14, FUN = mean, fill = NA, align = "right")]
}

dt <- na.omit(dt)
n_clean <- nrow(dt)
cat(sprintf("[INFO] %d observations after feature engineering\n", n_clean))

# ---- Method 1: Hidden Markov Model ----
if (args$method == "hmm") {
  cat(sprintf("[INFO] Running %d-state Hidden Markov Model ...\n", args$states))
  
  k <- args$states
  
  # EM algorithm for Gaussian HMM
  # Initialize parameters randomly
  set.seed(42)
  
  # Features for HMM: returns, volatility
  X <- cbind(dt$ret, dt$vol_20)
  
  # Initial state probabilities
  pi_k <- rep(1 / k, k)
  
  # Transition matrix (random init with strong diagonal)
  A <- matrix(0.1 / (k - 1), nrow = k, ncol = k)
  diag(A) <- 0.9
  
  # Emission parameters (mean, sd for each state)
  mu  <- quantile(dt$ret, probs = seq(0.1, 0.9, length.out = k))
  sigma <- rep(sd(dt$ret), k)
  
  # Helper: multivariate normal density
  dmvnorm <- function(x, mean, sd) {
    dnorm(x[1], mean, sd, log = TRUE) +
      dnorm(x[2], mean * 0.5, sd * 2, log = TRUE)
  }
  
  # Baum-Welch (EM) iterations
  max_iter <- 50
  tol      <- 1e-4
  log_lik_prev <- -Inf
  
  for (iter in seq_len(max_iter)) {
    # ---- E-step: Forward-Backward ----
    n_obs <- nrow(X)
    
    # Forward pass
    alpha <- matrix(0, nrow = n_obs, ncol = k)
    for (j in 1:k) {
      alpha[1, j] <- pi_k[j] * exp(dmvnorm(X[1, ], mu[j], sigma[j]))
    }
    alpha[1, ] <- alpha[1, ] / sum(alpha[1, ])
    
    for (t in 2:n_obs) {
      for (j in 1:k) {
        emission <- exp(dmvnorm(X[t, ], mu[j], sigma[j]))
        alpha[t, j] <- emission * sum(alpha[t - 1, ] * A[, j])
      }
      alpha[t, ] <- alpha[t, ] / sum(alpha[t, ])
    }
    
    # Backward pass
    beta <- matrix(0, nrow = n_obs, ncol = k)
    beta[n_obs, ] <- 1
    
    for (t in (n_obs - 1):1) {
      for (i in 1:k) {
        beta[t, i] <- 0
        for (j in 1:k) {
          emission <- exp(dmvnorm(X[t + 1, ], mu[j], sigma[j]))
          beta[t, i] <- beta[t, i] + A[i, j] * emission * beta[t + 1, j]
        }
      }
    }
    
    # Posterior probabilities (gamma)
    gamma <- matrix(0, nrow = n_obs, ncol = k)
    for (t in 1:n_obs) {
      gamma[t, ] <- alpha[t, ] * beta[t, ]
      gamma[t, ] <- gamma[t, ] / sum(gamma[t, ])
    }
    
    # Xi (transition posterior)
    xi <- array(0, dim = c(n_obs - 1, k, k))
    for (t in 1:(n_obs - 1)) {
      denom <- 0
      for (i in 1:k) {
        for (j in 1:k) {
          emission <- exp(dmvnorm(X[t + 1, ], mu[j], sigma[j]))
          xi[t, i, j] <- alpha[t, i] * A[i, j] * emission * beta[t + 1, j]
          denom <- denom + xi[t, i, j]
        }
      }
      xi[t, , ] <- xi[t, , ] / denom
    }
    
    # ---- M-step: Update parameters ----
    # Transition matrix
    for (i in 1:k) {
      for (j in 1:k) {
        A[i, j] <- sum(xi[, i, j]) / sum(gamma[-n_obs, i])
      }
    }
    
    # Emission parameters
    for (j in 1:k) {
      mu[j]    <- sum(gamma[, j] * X[, 1]) / sum(gamma[, j])
      sigma[j] <- sqrt(sum(gamma[, j] * (X[, 1] - mu[j]) ^ 2) / sum(gamma[, j]))
      sigma[j] <- max(sigma[j], 0.0001)  # prevent collapse
    }
    
    # Initial state
    pi_k <- gamma[1, ]
    
    # Log-likelihood
    log_lik <- 0
    for (t in 1:n_obs) {
      log_lik <- log_lik + log(sum(alpha[t, ] * beta[t, ]))
    }
    
    if (iter %% 10 == 0) {
      cat(sprintf("  Iteration %d: log-lik = %.2f\n", iter, log_lik))
    }
    
    if (abs(log_lik - log_lik_prev) < tol) {
      cat(sprintf("  Converged at iteration %d\n", iter))
      break
    }
    log_lik_prev <- log_lik
  }
  
  # Hard assignment (most likely state)
  regime <- apply(gamma, 1, which.max)
  
  # Label regimes by return characteristic
  state_ret <- sapply(1:k, function(j) mean(dt$ret[regime == j]) * 252)
  state_names <- c("Bear", "Range", "Bull")[rank(state_ret)]
  
  cat("\n=== HMM Regime Characteristics ===\n")
  for (j in 1:k) {
    idx <- which(regime == j)
    r    <- dt$ret[idx]
    cat(sprintf("  Regime %d (%s): n=%5d  ann_ret=%+.2f%%  vol=%.2f%%  freq=%.1f%%\n",
                j, state_names[j], length(idx),
                mean(r) * 252 * 100, sd(r) * sqrt(252) * 100,
                length(idx) / n_clean * 100))
  }
  
  cat(sprintf("\nTransition Matrix:\n"))
  rownames(A) <- colnames(A) <- sprintf("S%d_%s", 1:k, state_names)
  print(round(A, 3))
  
  dt[, regime_label := factor(state_names[regime], levels = c("Bull", "Range", "Bear"))]
}

# ---- Method 2: Volatility Clustering ----
if (args$method == "volatility") {
  cat(sprintf("[INFO] Running volatility clustering (window=%d) ...\n", args$window))
  
  vol_col <- if (has_ohlc && "gk_vol" %in% names(dt)) "gk_vol" else "vol_20"
  
  dt[, rolling_vol := rollapply(ret, width = args$window, FUN = sd,
                                fill = NA, align = "right")]
  dt <- na.omit(dt)
  n_clean <- nrow(dt)
  
  # Define volatility regimes by percentile
  vol_vec <- dt$rolling_vol
  lo_threshold <- quantile(vol_vec, 0.33, na.rm = TRUE)
  hi_threshold <- quantile(vol_vec, 0.67, na.rm = TRUE)
  
  dt[, vol_regime := fifelse(rolling_vol <= lo_threshold, "Low",
                      fifelse(rolling_vol >= hi_threshold, "High", "Medium"))]
  dt[, vol_regime := factor(vol_regime, levels = c("Low", "Medium", "High"))]
  
  cat(sprintf("\n=== Volatility Regime Thresholds ===\n"))
  cat(sprintf("  Low vol   <= %5.4f (33rd pctile)\n", lo_threshold))
  cat(sprintf("  High vol  >= %5.4f (67th pctile)\n", hi_threshold))
  
  # Regime statistics
  for (r in c("Low", "Medium", "High")) {
    idx <- which(dt$vol_regime == r)
    rr  <- dt$ret[idx]
    cat(sprintf("  Regime %s: n=%5d  ann_ret=%+.2f%%  vol=%.2f%%  freq=%.1f%%\n",
                r, length(idx),
                mean(rr) * 252 * 100, sd(rr) * sqrt(252) * 100,
                length(idx) / n_clean * 100))
  }
  
  # Volatility clustering persistence
  dt[, regime_shift := shift(vol_regime, 1)]
  pers_dt <- dt[!is.na(regime_shift)]
  for (r in c("Low", "Medium", "High")) {
    n_regime <- sum(pers_dt$vol_regime == r)
    n_stay   <- sum(pers_dt$vol_regime == r & pers_dt$regime_shift == r)
    cat(sprintf("  %s persistence: %.1f%% (stay / total)\n", r, n_stay / n_regime * 100))
  }
}

# ---- Plot ----
dt[, idx := .I]

# Plot 1: Price with regime background
p1 <- ggplot(dt, aes(x = idx, y = close)) +
  geom_line(color = "#2C3E50", linewidth = 0.4)

if (args$method == "hmm") {
  # HMM: color background by regime
  p1 <- p1 +
    geom_tile(aes(y = min(close), height = max(close) - min(close),
                  fill = regime_label), alpha = 0.15) +
    scale_fill_manual(name = "Regime",
                      values = c("Bull" = "#2ECC71", "Range" = "#F39C12", "Bear" = "#E74C3C"))
} else {
  # Volatility: color background by regime
  p1 <- p1 +
    geom_tile(aes(y = min(close), height = max(close) - min(close),
                  fill = vol_regime), alpha = 0.15) +
    scale_fill_manual(name = "Regime",
                      values = c("Low" = "#3498DB", "Medium" = "#F39C12", "High" = "#E74C3C"))
}

p1 <- p1 + labs(x = "", y = "Close Price", title = "Price & Market Regime Detection") +
  theme_minimal(base_size = 11)

# Plot 2: Returns by regime (boxplot)
if (args$method == "hmm") {
  p2 <- ggplot(dt, aes(x = regime_label, y = ret, fill = regime_label)) +
    geom_boxplot(outlier.size = 0.3, alpha = 0.7) +
    scale_fill_manual(values = c("Bull" = "#2ECC71", "Range" = "#F39C12", "Bear" = "#E74C3C"),
                      guide = "none") +
    labs(x = "", y = "Daily Return", title = "Return Distribution by Regime") +
    theme_minimal(base_size = 11)
} else {
  p2 <- ggplot(dt, aes(x = vol_regime, y = ret, fill = vol_regime)) +
    geom_boxplot(outlier.size = 0.3, alpha = 0.7) +
    scale_fill_manual(values = c("Low" = "#3498DB", "Medium" = "#F39C12", "High" = "#E74C3C"),
                      guide = "none") +
    labs(x = "", y = "Daily Return", title = "Return Distribution by Volatility Regime") +
    theme_minimal(base_size = 11)
}

# Plot 3: Volatility over time
p3 <- ggplot(dt, aes(x = idx, y = vol_20)) +
  geom_line(color = "#8E44AD", linewidth = 0.5) +
  labs(x = "Observation", y = "Rolling Volatility (20)",
       title = "Volatility Over Time") +
  theme_minimal(base_size = 11)

# Plot 4: Regime transitions (Sankey-like stacked bar)
if (args$method == "hmm") {
  trans_dt <- dt[, .N, by = .(regime_label)]
  trans_dt[, pct := N / sum(N)]
  
  p4 <- ggplot(trans_dt, aes(x = "", y = pct, fill = regime_label)) +
    geom_bar(stat = "identity", width = 1) +
    scale_fill_manual(values = c("Bull" = "#2ECC71", "Range" = "#F39C12", "Bear" = "#E74C3C")) +
    coord_polar("y", start = 0) +
    geom_text(aes(label = percent(pct, accuracy = 0.1)), position = position_stack(vjust = 0.5)) +
    labs(title = "Regime Distribution", fill = "Regime") +
    theme_void(base_size = 11) +
    theme(plot.title = element_text(hjust = 0.5))
} else {
  # Volatility clustering: autocorrelation of abs returns
  acf_vals <- acf(abs(dt$ret), plot = FALSE, lag.max = 60)
  acf_dt <- data.table(lag = acf_vals$lag, acf = acf_vals$acf)
  
  p4 <- ggplot(acf_dt[lag > 0], aes(x = lag, y = acf)) +
    geom_bar(stat = "identity", fill = "#8E44AD", alpha = 0.7, width = 0.6) +
    geom_hline(yintercept = c(-1.96 / sqrt(n_clean), 1.96 / sqrt(n_clean)),
               linetype = "dashed", color = "gray50") +
    labs(x = "Lag", y = "ACF", title = "Volatility Clustering (Abs Return ACF)") +
    theme_minimal(base_size = 11)
}

# Assemble
png(args$plot, width = 1600, height = 900, res = 140)
grid.arrange(p1, p2, p3, p4, ncol = 2, nrow = 2,
             top = sprintf("IST Market Regime Analysis (%s)", args$method))
dev.off()
cat(sprintf("[INFO] Plot saved to %s\n", args$plot))

cat("[DONE] Market regime analysis complete.\n")
