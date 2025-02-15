document.addEventListener("DOMContentLoaded", function () {
    const loginForm = document.getElementById("login-form");

    if (loginForm) {
        loginForm.addEventListener("submit", function (event) {
            event.preventDefault(); // Prevent page reload

            const email = document.getElementById("email").value;
            if (validateEmail(email)) {
                console.log("Logging in with:", email);
                alert("Login successful (simulation)");
            } else {
                alert("Please enter a valid email address.");
            }
        });
    }
});

// ✅ Validate email format
function validateEmail(email) {
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailPattern.test(email);
}

// ✅ Handle Social Login
function socialLogin(provider) {
    alert(`Logging in with ${provider} (simulation)`);
    console.log(`User clicked ${provider} login`);
}

// ✅ Handle File Selection
function displayFileName() {
    const fileInput = document.getElementById("file-input");
    const fileNameDisplay = document.getElementById("file-name");

    if (fileInput.files.length > 0) {
        fileNameDisplay.textContent = "Selected File: " + fileInput.files[0].name;
    } else {
        fileNameDisplay.textContent = "";
    }
}

// ✅ Handle File Upload & Start Analysis
async function uploadFile() {
    const fileInput = document.getElementById("file-input");
    const resultsDiv = document.getElementById("results");
    const analysisContent = document.getElementById("analysis-content");
    const downloadLink = document.getElementById("download-link");
    const loader = document.getElementById("loader");
    const processingText = document.getElementById("processing-text");

    if (!fileInput.files.length) {
        alert("Please select a file to upload.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    // ✅ Show Loader
    loader.style.display = "block";
    processingText.style.display = "block";
    resultsDiv.style.display = "none";

    try {
        // ✅ Start analysis & get Task ID
        const response = await fetch("/analyze", {
            method: "POST",
            body: formData
        });

        const result = await response.json();
        if (result.error) {
            throw new Error(result.error);
        }

        console.log("Analysis started, Task ID:", result.task_id);

        // ✅ Poll for results using Task ID
        checkStatus(result.task_id);

    } catch (error) {
        loader.style.display = "none";
        processingText.style.display = "none";
        alert(`An error occurred: ${error.message}`);
    }
}

// ✅ Poll API to Check Analysis Status
async function checkStatus(taskId) {
    const resultsDiv = document.getElementById("results");
    const analysisContent = document.getElementById("analysis-content");
    const downloadLink = document.getElementById("download-link");
    const loader = document.getElementById("loader");
    const processingText = document.getElementById("processing-text");

    while (true) {
        try {
            const response = await fetch(`/analysis_status/${taskId}`);
            const result = await response.json();

            if (result.status && result.status.includes("Processing")) {
                console.log("Still processing...");
                await new Promise(resolve => setTimeout(resolve, 5000)); // Wait 5 seconds before retrying
            } else {
                // ✅ Hide Loader & Show Results
                loader.style.display = "none";
                processingText.style.display = "none";
                resultsDiv.style.display = "block";

                // ✅ Display Analysis or Error Message
                if (result.analysis) {
                    analysisContent.innerHTML = `<div class="section-content">${result.analysis.replace(/\n/g, "<br>")}</div>`;
                    downloadLink.href = result.download_link;
                    downloadLink.style.display = "inline-block";
                } else {
                    analysisContent.innerHTML = `<p style='color:red;'>Error: ${result.error}</p>`;
                }
                break;
            }
        } catch (error) {
            console.error("Error checking status:", error);
            break;
        }
    }
}
