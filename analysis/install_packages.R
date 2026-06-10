# ---------------------------------------------------------------------------
# install_packages.R — R Package Dependency Management for IST Platform
#
# Usage:
#   Rscript analysis/install_packages.R
#
# Installs all required R packages for IST analysis scripts.
# Uses CRAN mirror from .Rprofile or defaults to cloud mirror.
# ---------------------------------------------------------------------------

# Set CRAN mirror
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Required packages by script
required_packages <- list(
  performance           = c("optparse", "ggplot2", "data.table", "gridExtra", "zoo"),
  monte_carlo           = c("optparse", "ggplot2", "data.table"),
  portfolio_optimization = c("optparse", "quadprog", "ggplot2", "data.table", "scales"),
  risk_decomposition    = c("optparse", "ggplot2", "data.table", "gridExtra", "scales"),
  market_regime         = c("optparse", "ggplot2", "data.table", "gridExtra", "scales", "zoo")
)

# Flatten unique list
all_packages <- unique(unlist(required_packages, use.names = FALSE))

cat("=== IST R Package Dependency Manager ===\n")
cat(sprintf("Total unique packages required: %d\n", length(all_packages)))

# Check installed
installed <- rownames(installed.packages())
missing   <- setdiff(all_packages, installed)
installed_found <- intersect(all_packages, installed)

cat(sprintf("  Already installed: %d\n", length(installed_found)))
cat(sprintf("  Need to install:   %d\n", length(missing)))

if (length(missing) > 0) {
  cat(sprintf("\nInstalling: %s\n", paste(missing, collapse = ", ")))
  install.packages(missing, dependencies = TRUE)
}

# Verify
cat("\n=== Verification ===\n")
all_ok <- TRUE
for (pkg in all_packages) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    ver <- as.character(packageVersion(pkg))
    cat(sprintf("  [ OK ] %-20s v%s\n", pkg, ver))
  } else {
    cat(sprintf("  [FAIL] %s\n", pkg))
    all_ok <- FALSE
  }
}

if (all_ok) {
  cat(sprintf("\nAll %d packages installed successfully.\n", length(all_packages)))
} else {
  cat("\nSome packages failed to install. Check error messages above.\n")
}

# Print script-to-package mapping
cat("\n=== Package Usage by Script ===\n")
for (script in names(required_packages)) {
  cat(sprintf("  %-25s <- %s\n", script, paste(required_packages[[script]], collapse = ", ")))
}
