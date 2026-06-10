#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# portfolio_optimization.R — Mean-Variance & Black-Litterman Portfolio Optimization
#
# Usage:
#   # Markowitz efficient frontier from CSV returns
#   Rscript analysis/portfolio_optimization.R \
#     --returns=data/portfolio_returns.csv \
#     --method=markowitz \
#     --risk-free=0.03 \
#     --plot=ef_frontier.png
#
#   # Black-Litterman with investor views
#   Rscript analysis/portfolio_optimization.R \
#     --returns=data/portfolio_returns.csv \
#     --method=black-litterman \
#     --views=data/bl_views.csv \
#     --tau=0.025 \
#     --plot=bl_allocation.png
#
#   # CSV format for --returns: rows=dates, columns=assets, values=returns
#   # CSV format for --views:   asset, view_return, confidence
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(optparse)
  library(quadprog)
  library(ggplot2)
  library(data.table)
  library(scales)
})

# ---- CLI ----
option_list <- list(
  make_option("--returns",    type = "character", default = "data/portfolio_returns.csv",
              help = "Path to asset returns CSV [default %default]"),
  make_option("--method",     type = "character", default = "markowitz",
              help = "Optimization method: markowitz | black-litterman [default %default]"),
  make_option("--risk-free",  type = "numeric",   default = 0.03,
              help = "Annual risk-free rate [default %default]"),
  make_option("--views",      type = "character", default = NULL,
              help = "Path to Black-Litterman views CSV [default NULL]"),
  make_option("--tau",        type = "numeric",   default = 0.025,
              help = "BL uncertainty scaling factor [default %default]"),
  make_option("--plot",       type = "character", default = "portfolio_optimization.png",
              help = "Output plot path [default %default]"),
  make_option("--csv",        type = "character", default = NULL,
              help = "Output allocation CSV path [default NULL]")
)
parser <- OptionParser(option_list = option_list,
                       description = "Portfolio optimization for IST Platform")
args <- parse_args(parser)

# ---- Load Returns Data ----
cat(sprintf("[INFO] Loading returns from %s ...\n", args$returns))
if (!file.exists(args$returns)) stop(sprintf("File not found: %s", args$returns))

ret_dt <- fread(args$returns)
asset_names <- setdiff(names(ret_dt), c("date", "Date", "DATE"))
if (length(asset_names) < 2) stop("Need at least 2 asset columns in returns CSV")

ret_mat <- as.matrix(ret_dt[, ..asset_names])
n_assets <- length(asset_names)
n_obs    <- nrow(ret_mat)

cat(sprintf("[INFO] %d assets, %d observations\n", n_assets, n_obs))

# ---- Core Statistics ----
mean_ret <- colMeans(ret_mat) * 252          # annualized
cov_mat  <- cov(ret_mat) * 252               # annualized
rf_annual <- args[["risk-free"]]

cat("\n=== Asset Statistics ===\n")
for (i in seq_len(n_assets)) {
  vol <- sqrt(cov_mat[i, i])
  cat(sprintf("  %-20s  ret=%+.2f%%  vol=%.2f%%  sharpe=%.3f\n",
              asset_names[i],
              mean_ret[i] * 100,
              vol * 100,
              (mean_ret[i] - rf_annual) / vol))
}

# ---- Mean-Variance Optimization ----
markowitz_optimal <- function(mean_ret, cov_mat, rf, target_return) {
  n <- length(mean_ret)
  Dmat <- 2 * cov_mat
  dvec <- rep(0, n)
  Amat <- cbind(rep(1, n), mean_ret, diag(n))
  bvec <- c(1, target_return, rep(0, n))
  
  sol <- tryCatch(
    solve.QP(Dmat, dvec, Amat, bvec, meq = 2),
    error = function(e) NULL
  )
  
  if (is.null(sol)) return(NULL)
  
  w <- sol$solution
  w <- pmax(w, 0)
  w <- w / sum(w)
  
  port_ret   <- sum(w * mean_ret)
  port_vol   <- sqrt(t(w) %*% cov_mat %*% w)
  port_sharpe <- (port_ret - rf) / port_vol
  
  list(weights = w, ret = port_ret, vol = port_vol, sharpe = port_sharpe)
}

# ---- Efficient Frontier ----
cat(sprintf("\n[INFO] Computing efficient frontier ...\n"))

min_ret <- min(mean_ret)
max_ret <- max(mean_ret)

# Minimum variance portfolio
mvp <- markowitz_optimal(mean_ret, cov_mat, rf_annual, min_ret)
if (is.null(mvp)) stop("Optimization failed — check return data for collinearity")

# Tangency portfolio (max Sharpe)
targets <- seq(min_ret, max_ret, length.out = 100)
frontier <- data.table(ret = numeric(), vol = numeric(), sharpe = numeric())

max_sharpe <- -Inf
tangency  <- mvp

for (tgt in targets) {
  opt <- markowitz_optimal(mean_ret, cov_mat, rf_annual, tgt)
  if (!is.null(opt)) {
    frontier <- rbind(frontier, data.table(ret = opt$ret, vol = opt$vol, sharpe = opt$sharpe))
    if (opt$sharpe > max_sharpe) {
      max_sharpe <- opt$sharpe
      tangency  <- opt
    }
  }
}

cat(sprintf("[INFO] Efficient frontier: %d points computed\n", nrow(frontier)))
cat(sprintf("  Minimum Variance Portfolio:  ret=%+.2f%%  vol=%.2f%%\n",
            mvp$ret * 100, mvp$vol * 100))
cat(sprintf("  Tangency Portfolio:          ret=%+.2f%%  vol=%.2f%%  sharpe=%.3f\n",
            tangency$ret * 100, tangency$vol * 100, tangency$sharpe))

cat("\nTangency Portfolio Weights:\n")
for (i in seq_len(n_assets)) {
  cat(sprintf("  %-20s %6.2f%%\n", asset_names[i], tangency$weights[i] * 100))
}

# ---- Black-Litterman Extension ----
if (args$method == "black-litterman") {
  cat(sprintf("\n[INFO] Running Black-Litterman model (tau=%.4f) ...\n", args$tau))
  
  # Equilibrium returns (implied by market-cap weights — use equal-weight as prior)
  w_eq    <- rep(1 / n_assets, n_assets)
  pi_eq   <- rf_annual + cov_mat %*% w_eq * 2.5  # market risk aversion = 2.5
  
  # Investor views
  if (!is.null(args$views) && file.exists(args$views)) {
    views_dt <- fread(args$views)
    P <- matrix(0, nrow = nrow(views_dt), ncol = n_assets)
    Q <- rep(0, nrow(views_dt))
    omega <- diag(nrow(views_dt))
    
    for (i in seq_len(nrow(views_dt))) {
      asset_idx <- which(asset_names == views_dt[i, asset])
      if (length(asset_idx) > 0) {
        P[i, asset_idx] <- 1
      }
      Q[i] <- views_dt[i, view_return]
      omega[i, i] <- 1 / views_dt[i, confidence]
    }
    
    cat(sprintf("[INFO] Loaded %d investor views\n", nrow(views_dt)))
  } else {
    # Default views: mean reversion to historical averages
    P <- diag(n_assets)
    Q <- mean_ret
    omega <- diag(n_assets) * 0.25
    cat("[INFO] Using default views (historical mean returns)\n")
  }
  
  # Black-Litterman posterior
  tau_sigma <- args$tau * cov_mat
  M_inv <- solve(tau_sigma)
  
  posterior_var <- solve(M_inv + t(P) %*% solve(omega) %*% P)
  posterior_mean <- posterior_var %*% (M_inv %*% pi_eq + t(P) %*% solve(omega) %*% Q)
  
  posterior_mean <- as.vector(posterior_mean)
  
  # Optimize with posterior estimates
  bl_tangency <- markowitz_optimal(posterior_mean, cov_mat, rf_annual, mean(posterior_mean))
  
  cat("Prior (Equilibrium) Returns vs Posterior Returns:\n")
  for (i in seq_len(n_assets)) {
    cat(sprintf("  %-20s  prior=%+.2f%% -> posterior=%+.2f%%\n",
                asset_names[i], pi_eq[i] * 100, posterior_mean[i] * 100))
  }
  
  cat("\nBlack-Litterman Optimal Weights:\n")
  if (!is.null(bl_tangency)) {
    for (i in seq_len(n_assets)) {
      cat(sprintf("  %-20s %6.2f%%\n", asset_names[i], bl_tangency$weights[i] * 100))
    }
    cat(sprintf("  Expected Return: %+.2f%%  Vol: %.2f%%  Sharpe: %.3f\n",
                bl_tangency$ret * 100, bl_tangency$vol * 100, bl_tangency$sharpe))
  }
  
  # Use BL weights for CSV export
  optimal_weights <- if (!is.null(bl_tangency)) bl_tangency$weights else tangency$weights
} else {
  optimal_weights <- tangency$weights
}

# ---- Plot ----
# Plot 1: Efficient Frontier
p1 <- ggplot(frontier, aes(x = vol, y = ret)) +
  geom_line(color = "#3498DB", linewidth = 0.8) +
  geom_point(aes(x = vol, y = ret), data = data.table(vol = mvp$vol, ret = mvp$ret),
             color = "#F39C12", size = 3, shape = 18) +
  geom_point(aes(x = vol, y = ret), data = data.table(vol = tangency$vol, ret = tangency$ret),
             color = "#E74C3C", size = 3, shape = 17) +
  geom_abline(intercept = rf_annual, slope = tangency$sharpe,
              linetype = "dashed", color = "gray50", linewidth = 0.5) +
  annotate("text", x = mvp$vol * 1.02, y = mvp$ret, label = "MVP",
           color = "#F39C12", hjust = 0, size = 3.5) +
  annotate("text", x = tangency$vol * 1.02, y = tangency$ret, label = "Tangency",
           color = "#E74C3C", hjust = 0, size = 3.5) +
  labs(x = "Annualized Volatility", y = "Annualized Return",
       title = "Efficient Frontier & Optimal Portfolios") +
  scale_x_continuous(labels = percent) +
  scale_y_continuous(labels = percent) +
  theme_minimal(base_size = 12)

# Plot 2: Allocation pie chart
alloc_dt <- data.table(
  asset = factor(asset_names, levels = asset_names),
  weight = tangency$weights
)

p2 <- ggplot(alloc_dt, aes(x = "", y = weight, fill = asset)) +
  geom_bar(stat = "identity", width = 1, color = "white") +
  coord_polar("y", start = 0) +
  geom_text(aes(label = ifelse(weight > 0.03, percent(weight, accuracy = 0.1), "")),
            position = position_stack(vjust = 0.5), size = 3.5) +
  labs(title = "Tangency Portfolio Allocation", fill = "Asset") +
  theme_void(base_size = 12) +
  theme(plot.title = element_text(hjust = 0.5))

# Combine plots
png(args$plot, width = 1400, height = 700, res = 140)
layout(matrix(c(1, 2), nrow = 1), widths = c(3, 2))
print(p1, newpage = FALSE)
print(p2, newpage = FALSE)
dev.off()
cat(sprintf("[INFO] Plot saved to %s\n", args$plot))

# ---- CSV Export ----
if (!is.null(args$csv)) {
  export_dt <- data.table(Asset = asset_names, Weight = optimal_weights)
  fwrite(export_dt, args$csv)
  cat(sprintf("[INFO] Allocation saved to %s\n", args$csv))
}

cat("[DONE] Portfolio optimization complete.\n")
