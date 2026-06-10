#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# risk_decomposition.R — Factor Risk Decomposition & VaR Contribution Analysis
#
# Usage:
#   Rscript analysis/risk_decomposition.R \
#     --returns=data/portfolio_returns.csv \
#     --factors=data/factor_returns.csv \
#     --weights=data/portfolio_weights.csv \
#     --plot=risk_decomposition.png
#
#   CSV format for --returns:  rows=dates, columns=assets, values=returns
#   CSV format for --factors:  rows=dates, columns=factor1|factor2|..., values=returns
#   CSV format for --weights:  rows=assets, columns=Weight, values=allocation
# ---------------------------------------------------------------------------

suppressPackageStartupMessages({
  library(optparse)
  library(ggplot2)
  library(data.table)
  library(gridExtra)
  library(scales)
})

# ---- CLI ----
option_list <- list(
  make_option("--returns",  type = "character", default = "data/portfolio_returns.csv",
              help = "Path to asset returns CSV [default %default]"),
  make_option("--factors",  type = "character", default = NULL,
              help = "Path to factor returns CSV [default NULL]"),
  make_option("--weights",  type = "character", default = NULL,
              help = "Path to portfolio weights CSV [default NULL]"),
  make_option("--conf-level", type = "numeric", default = 0.95,
              help = "Confidence level for VaR [default %default]"),
  make_option("--plot",     type = "character", default = "risk_decomposition.png",
              help = "Output plot path [default %default]")
)
parser <- OptionParser(option_list = option_list,
                       description = "Risk decomposition analytics for IST Platform")
args <- parse_args(parser)

# ---- Load Data ----
cat(sprintf("[INFO] Loading asset returns from %s ...\n", args$returns))
if (!file.exists(args$returns)) stop(sprintf("File not found: %s", args$returns))

ret_dt <- fread(args$returns)
asset_names <- setdiff(names(ret_dt), c("date", "Date", "DATE"))
n_assets <- length(asset_names)
ret_mat <- as.matrix(ret_dt[, ..asset_names])

# Portfolio weights
if (!is.null(args$weights) && file.exists(args$weights)) {
  w_dt <- fread(args$weights)
  w <- w_dt$Weight
  names(w) <- w_dt$Asset
  w <- w[asset_names]
  w[is.na(w)] <- 0
  w <- w / sum(w)
} else {
  w <- rep(1 / n_assets, n_assets)
  names(w) <- asset_names
}

cat(sprintf("[INFO] %d assets, equal-weight applied\n", n_assets))
for (i in seq_len(n_assets)) {
  cat(sprintf("  %-20s weight=%6.2f%%\n", asset_names[i], w[i] * 100))
}

# ---- Portfolio Returns ----
port_ret <- as.vector(ret_mat %*% w)
n_obs    <- length(port_ret)

ann_ret <- mean(port_ret) * 252
ann_vol <- sd(port_ret) * sqrt(252)
sharpe  <- ann_ret / ann_vol

cat(sprintf("\n=== Portfolio Summary ===\n"))
cat(sprintf("  Annualized Return:  %+.2f%%\n", ann_ret * 100))
cat(sprintf("  Annualized Vol:      %.2f%%\n", ann_vol * 100))
cat(sprintf("  Sharpe Ratio:         %.3f\n", sharpe))

# ---- VaR & CVaR ----
alpha <- 1 - args[["conf-level"]]
var_hist   <- quantile(port_ret, alpha)
cvar_hist  <- mean(port_ret[port_ret <= var_hist])

# Parametric VaR (assuming normality)
var_param  <- mean(port_ret) + qnorm(alpha) * sd(port_ret)
cvar_param <- mean(port_ret) - dnorm(qnorm(1 - alpha)) / alpha * sd(port_ret)

cat(sprintf("\n=== Value-at-Risk (%.0f%% confidence) ===\n", args[["conf-level"]] * 100))
cat(sprintf("  Historical VaR  (daily): %+.4f%%\n", var_hist * 100))
cat(sprintf("  Historical CVaR (daily): %+.4f%%\n", cvar_hist * 100))
cat(sprintf("  Parametric VaR  (daily): %+.4f%%\n", var_param * 100))
cat(sprintf("  Parametric CVaR (daily): %+.4f%%\n", cvar_param * 100))

# ---- Factor Risk Decomposition ----
if (!is.null(args$factors) && file.exists(args$factors)) {
  cat(sprintf("\n[INFO] Loading factor returns from %s ...\n", args$factors))
  
  factor_dt <- fread(args$factors)
  factor_names <- setdiff(names(factor_dt), c("date", "Date", "DATE"))
  factor_mat <- as.matrix(factor_dt[, ..factor_names])
  
  if (nrow(factor_mat) == 0) stop("Factor CSV is empty or has header-only")
  
  # Ensure alignment of asset and factor returns
  common_rows <- min(nrow(ret_mat), nrow(factor_mat))
  
  # Factor exposures via OLS regression: R_asset = alpha + Beta * F + epsilon
  exposures <- matrix(NA_real_, nrow = n_assets, ncol = length(factor_names))
  rownames(exposures) <- asset_names
  colnames(exposures) <- factor_names
  r_squared   <- rep(NA_real_, n_assets)
  
  for (i in seq_len(n_assets)) {
    asset_ret <- ret_mat[1:common_rows, i]
    model <- lm(asset_ret ~ factor_mat[1:common_rows, ])
    exposures[i, ] <- coef(model)[-1]
    r_squared[i] <- summary(model)$r.squared
  }
  
  cat("\n=== Factor Exposures ===\n")
  print(round(exposures, 4))
  
  # Factor-based risk decomposition
  # Portfolio risk = sqrt(w' * (Beta * Sigma_f * Beta' + D) * w)
  factor_cov <- cov(factor_mat[1:common_rows, ])
  residual_var <- rep(NA_real_, n_assets)
  
  for (i in seq_len(n_assets)) {
    asset_ret <- ret_mat[1:common_rows, i]
    fitted <- factor_mat[1:common_rows, ] %*% exposures[i, ]
    residual_var[i] <- var(asset_ret - fitted)
  }
  
  # Systematic risk
  systematic_var <- as.numeric(t(w) %*% exposures %*% factor_cov %*% t(exposures) %*% w)
  # Idiosyncratic risk
  idio_var <- as.numeric(t(w) %*% diag(residual_var) %*% w)
  
  total_var <- systematic_var + idio_var
  sys_pct   <- systematic_var / total_var * 100
  idio_pct  <- idio_var / total_var * 100
  
  cat(sprintf("\n=== Risk Decomposition (Annualized) ===\n"))
  cat(sprintf("  Total Risk:            %.2f%%\n", sqrt(total_var * 252) * 100))
  cat(sprintf("  Systematic Risk:       %.2f%% (%4.1f%%)\n",
              sqrt(systematic_var * 252) * 100, sys_pct))
  cat(sprintf("  Idiosyncratic Risk:    %.2f%% (%4.1f%%)\n",
              sqrt(idio_var * 252) * 100, idio_pct))
  
  # Factor contribution to systematic risk
  factor_contrib <- rep(NA_real_, length(factor_names))
  names(factor_contrib) <- factor_names
  
  for (j in seq_along(factor_names)) {
    beta_j <- exposures[, j]
    contrib <- 0
    for (k in seq_along(factor_names)) {
      contrib <- contrib + beta_j[k] * factor_cov[j, k] * beta_j[k]
    }
    factor_contrib[j] <- contrib * w[j] * w[j] / systematic_var * sys_pct / 100
  }
  
  cat("\nFactor Contribution to Systematic Risk:\n")
  for (j in seq_along(factor_names)) {
    cat(sprintf("  %-20s %5.1f%%\n", factor_names[j], factor_contrib[j] * 100))
  }
  
  has_factors <- TRUE
} else {
  cat("[INFO] No factor CSV provided — skipping factor decomposition\n")
  has_factors <- FALSE
}

# ---- VaR Contribution (Marginal & Component) ----
cat(sprintf("\n=== VaR Contribution Analysis ===\n"))

# Marginal VaR: dVaR/dw_i = mu_i + (rho_i * sigma_i / sigma_p) * (VaR_p - mu_p)
port_mu    <- mean(port_ret)
port_sigma <- sd(port_ret)
port_var   <- var_hist

marginal_var <- rep(NA_real_, n_assets)
component_var <- rep(NA_real_, n_assets)
names(marginal_var) <- asset_names
names(component_var) <- asset_names

for (i in seq_len(n_assets)) {
  asset_mu    <- mean(ret_mat[, i])
  asset_sigma <- sd(ret_mat[, i])
  rho_i       <- cor(ret_mat[, i], port_ret)
  
  # Marginal VaR
  marginal_var[i] <- asset_mu + (rho_i * asset_sigma / port_sigma) * (port_var - port_mu)
  
  # Component VaR = w_i * Marginal VaR
  component_var[i] <- w[i] * marginal_var[i]
}

# Normalize to 100%
component_var_pct <- component_var / sum(abs(component_var)) * 100

# Percent contribution to total VaR
for (i in seq_len(n_assets)) {
  cat(sprintf("  %-20s  marginal_vaR=%.4f  component_var=%.4f  pct_contrib=%+.1f%%\n",
              asset_names[i], marginal_var[i], component_var[i], component_var_pct[i]))
}

# ---- Plot ----
plot_list <- list()

# Plot 1: Portfolio return distribution with VaR
ret_df <- data.table(ret = port_ret)
p1 <- ggplot(ret_df, aes(x = ret)) +
  geom_histogram(aes(y = after_stat(density)), bins = 50,
                 fill = "#34495E", alpha = 0.7) +
  geom_density(color = "#3498DB", linewidth = 1) +
  geom_vline(xintercept = var_hist, color = "#E74C3C", linetype = "dashed", linewidth = 1) +
  geom_vline(xintercept = cvar_hist, color = "#C0392B", linetype = "dotted", linewidth = 0.8) +
  annotate("text", x = var_hist * 1.15, y = 0.5, label = sprintf("VaR %.0f%%", args[["conf-level"]] * 100),
           color = "#E74C3C", hjust = 0, size = 3.5) +
  labs(x = "Daily Return", y = "Density", title = "Portfolio Return Distribution with VaR") +
  theme_minimal(base_size = 11)

# Plot 2: VaR contribution by asset
var_contrib_df <- data.table(
  asset = factor(asset_names, levels = asset_names[order(component_var_pct, decreasing = TRUE)]),
  pct   = component_var_pct[order(component_var_pct, decreasing = TRUE)]
)

p2 <- ggplot(var_contrib_df, aes(x = asset, y = pct, fill = pct > 0)) +
  geom_bar(stat = "identity") +
  scale_fill_manual(values = c("TRUE" = "#E74C3C", "FALSE" = "#2ECC71"), guide = "none") +
  labs(x = "", y = "VaR Contribution (%)",
       title = sprintf("Component VaR (%.0f%% Confidence)", args[["conf-level"]] * 100)) +
  coord_flip() +
  theme_minimal(base_size = 11)

# Plot 3: Risk decomposition (factor vs idiosyncratic) — if factors provided
if (has_factors) {
  risk_decomp_df <- rbind(
    data.table(type = "Factor", factor = factor_names, value = factor_contrib[order(abs(factor_contrib), decreasing = TRUE)] * 100),
    data.table(type = "Idio", factor = "Idiosyncratic", value = idio_pct)
  )
  risk_decomp_df <- risk_decomp_df[order(abs(risk_decomp_df$value), decreasing = TRUE), ]
  risk_decomp_df$factor <- factor(risk_decomp_df$factor, levels = unique(risk_decomp_df$factor))
  
  p3 <- ggplot(risk_decomp_df, aes(x = factor, y = value, fill = type)) +
    geom_bar(stat = "identity") +
    scale_fill_manual(values = c("Factor" = "#3498DB", "Idio" = "#95A5A6")) +
    labs(x = "", y = "Risk Contribution (%)",
         title = "Risk Decomposition: Systematic vs Idiosyncratic") +
    coord_flip() +
    theme_minimal(base_size = 11)
  
  plot_list <- list(p1, p2, p3)
} else {
  plot_list <- list(p1, p2)
}

# Drawdown analysis
cum_eq <- exp(cumsum(port_ret))
dd_vec <- cum_eq / cummax(cum_eq) - 1
max_dd <- min(dd_vec)

cat(sprintf("\n=== Drawdown Analysis ===\n"))
cat(sprintf("  Max Drawdown:  %+.2f%%\n", max_dd * 100))
cat(sprintf("  Current DD:    %+.2f%%\n", tail(dd_vec, 1) * 100))

# Plot 4: Drawdown over time
dd_df <- data.table(idx = seq_len(length(dd_vec)), dd = dd_vec)

p4 <- ggplot(dd_df, aes(x = idx, y = dd)) +
  geom_ribbon(aes(ymin = 0, ymax = dd), fill = "#E74C3C", alpha = 0.25) +
  geom_line(color = "#E74C3C", linewidth = 0.5) +
  scale_y_continuous(labels = percent) +
  labs(x = "Observation", y = "Drawdown", title = "Portfolio Drawdown Over Time") +
  theme_minimal(base_size = 11)

plot_list <- c(plot_list, list(p4))

# Assemble
n_plots <- length(plot_list)
ncol <- if (n_plots == 4) 2 else min(n_plots, 3)
nrow <- ceiling(n_plots / ncol)

png(args$plot, width = 1600, height = 400 * nrow, res = 140)
grid.arrange(grobs = plot_list, ncol = ncol, nrow = nrow,
             top = "IST Risk Decomposition Report")
dev.off()
cat(sprintf("[INFO] Plot saved to %s\n", args$plot))

cat("[DONE] Risk decomposition analysis complete.\n")
