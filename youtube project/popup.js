// Get the DOM elements
const btn = document.getElementById("summarise");
const output = document.getElementById("output");
const videoUrlInput = document.getElementById("video-url");

// Function to handle the summarization request
async function handleSummarization() {
    const url = videoUrlInput.value.trim();

    if (!url) {
        output.innerHTML = "<span style='color: orange;'>Please paste a YouTube URL or navigate to a video page.</span>";
        return;
    }
    
    // Disable button and show loading state
    btn.disabled = true;
    output.innerHTML = "<span style='color: #3B82F6;'>Loading transcript and summarizing... (This may take 10-30 seconds)</span>";

    try {
        // Use fetch API for a modern, promise-based request
        const response = await fetch("http://127.0.0.1:5000/summary?url=" + encodeURIComponent(url));
        
        const data = await response.json();

        if (response.ok) {
            // Success: Display the summary
            output.innerHTML = "<strong>Summary:</strong><br><p>" + data.summary + "</p>";
        } else {
            // Server Error (e.g., 404 No Transcript, 500 Internal Error)
            output.innerHTML = "<span style='color: red;'>Error: " + data.error + "</span>";
        }

    } catch (error) {
        // Network or connection error (e.g., Flask server is not running)
        console.error("Fetch error:", error);
        output.innerHTML = "<span style='color: red;'>Error: Could not connect to the summarization service. Is the Python server running?</span>";
    } finally {
        // Re-enable button after operation completes (success or failure)
        btn.disabled = false;
        btn.innerHTML = "Summarise";
    }
}


// New approach: Use the URL from the input field AND the active tab as a fallback
btn.addEventListener("click", handleSummarization);

// Get the active tab's URL on load and populate the input field (optional)
chrome.tabs.query({currentWindow: true, active: true}, function(tabs){
    if (tabs[0] && tabs[0].url && tabs[0].url.includes("youtube.com/watch")) {
        videoUrlInput.value = tabs[0].url;
    }
});