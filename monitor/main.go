package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"sync"
	"syscall"
	"time"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/mem"
)

// HealthStatus represents the health check response.
type HealthStatus struct {
	Status    string `json:"status"`
	Timestamp string `json:"timestamp"`
	Uptime    string `json:"uptime"`
	Version   string `json:"version"`
	GoVersion string `json:"go_version"`
}

// SystemMetrics represents collected system metrics.
type SystemMetrics struct {
	CPUPercent    float64 `json:"cpu_percent"`
	MemoryUsedMB  uint64  `json:"memory_used_mb"`
	MemoryTotalMB uint64  `json:"memory_total_mb"`
	MemoryPct     float64 `json:"memory_pct"`
	Goroutines    int     `json:"goroutines"`
	NumCPU        int     `json:"num_cpu"`
	Timestamp     string  `json:"timestamp"`
}

// LatencyRecord tracks API response latencies.
type LatencyRecord struct {
	Endpoint   string  `json:"endpoint"`
	MeanMs     float64 `json:"mean_ms"`
	P50Ms      float64 `json:"p50_ms"`
	P95Ms      float64 `json:"p95_ms"`
	P99Ms      float64 `json:"p99_ms"`
	SampleSize int     `json:"sample_size"`
	Timestamp  string  `json:"timestamp"`
}

var (
	startTime   time.Time
	latencyMu   sync.RWMutex
	latencies   = make(map[string][]float64)
	version     = "1.0.0"
)

func main() {
	startTime = time.Now()
	port := getEnv("MONITOR_PORT", "9090")

	mux := http.NewServeMux()

	// Register routes
	mux.HandleFunc("/health", corsMiddleware(healthHandler))
	mux.HandleFunc("/metrics", corsMiddleware(metricsHandler))
	mux.HandleFunc("/latency", corsMiddleware(latencyHandler))
	mux.HandleFunc("/latency/record", corsMiddleware(latencyRecordHandler))

	addr := fmt.Sprintf(":%s", port)

	// Graceful shutdown
	server := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Listen for shutdown signals
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan
		log.Println("Shutting down monitor server...")
		server.Close()
	}()

	log.Printf("🔍 System monitor starting on %s (Go %s)", addr, runtime.Version())
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Monitor server error: %v", err)
	}
}

// healthHandler returns service health information.
func healthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	status := HealthStatus{
		Status:    "healthy",
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		Uptime:    time.Since(startTime).Round(time.Second).String(),
		Version:   version,
		GoVersion: runtime.Version(),
	}

	writeJSON(w, http.StatusOK, status)
}

// metricsHandler collects and returns current system metrics.
func metricsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	cpuPercent, err := cpu.Percent(time.Second, false)
	if err != nil {
		cpuPercent = []float64{0}
	}

	memInfo, err := mem.VirtualMemory()
	if err != nil {
		http.Error(w, "failed to read memory", http.StatusInternalServerError)
		return
	}

	metrics := SystemMetrics{
		CPUPercent:    round(cpuPercent[0], 2),
		MemoryUsedMB:  memInfo.Used / 1024 / 1024,
		MemoryTotalMB: memInfo.Total / 1024 / 1024,
		MemoryPct:     round(memInfo.UsedPercent, 2),
		Goroutines:    runtime.NumGoroutine(),
		NumCPU:        runtime.NumCPU(),
		Timestamp:     time.Now().UTC().Format(time.RFC3339),
	}

	writeJSON(w, http.StatusOK, metrics)
}

// latencyHandler returns collected latency statistics.
func latencyHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	latencyMu.RLock()
	defer latencyMu.RUnlock()

	results := make([]LatencyRecord, 0, len(latencies))
	for endpoint, samples := range latencies {
		if len(samples) == 0 {
			continue
		}
		sorted := make([]float64, len(samples))
		copy(sorted, samples)
		sortFloat64s(sorted)

		n := len(sorted)
		mean := sum(sorted) / float64(n)
		p50 := sorted[n*50/100]
		p95 := sorted[n*95/100]
		p99 := sorted[n*99/100]

		results = append(results, LatencyRecord{
			Endpoint:   endpoint,
			MeanMs:     round(mean, 3),
			P50Ms:      round(p50, 3),
			P95Ms:      round(p95, 3),
			P99Ms:      round(p99, 3),
			SampleSize: n,
			Timestamp:  time.Now().UTC().Format(time.RFC3339),
		})
	}

	if results == nil {
		results = []LatencyRecord{}
	}

	writeJSON(w, http.StatusOK, results)
}

// latencyRecordHandler records a latency sample for a given endpoint.
func latencyRecordHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var payload struct {
		Endpoint string  `json:"endpoint"`
		Latency  float64 `json:"latency_ms"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}
	if payload.Endpoint == "" || payload.Latency <= 0 {
		http.Error(w, "endpoint and positive latency_ms required", http.StatusBadRequest)
		return
	}

	latencyMu.Lock()
	latencies[payload.Endpoint] = append(latencies[payload.Endpoint], payload.Latency)
	// Keep at most 10000 samples per endpoint
	if len(latencies[payload.Endpoint]) > 10000 {
		latencies[payload.Endpoint] = latencies[payload.Endpoint][len(latencies[payload.Endpoint])-5000:]
	}
	latencyMu.Unlock()

	writeJSON(w, http.StatusAccepted, map[string]string{"status": "recorded"})
}

// corsMiddleware adds CORS headers.
func corsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next(w, r)
	}
}

// --- helpers ---

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(data); err != nil {
		log.Printf("encode error: %v", err)
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func round(v float64, decimals int) float64 {
	scale := 1.0
	for i := 0; i < decimals; i++ {
		scale *= 10
	}
	return float64(int64(v*scale+0.5)) / scale
}

func sum(s []float64) float64 {
	total := 0.0
	for _, v := range s {
		total += v
	}
	return total
}

func sortFloat64s(a []float64) {
	for i := 0; i < len(a); i++ {
		for j := i + 1; j < len(a); j++ {
			if a[i] > a[j] {
				a[i], a[j] = a[j], a[i]
			}
		}
	}
}