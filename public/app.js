// 🚀 Updated Frontend JavaScript with Backend API URL Integration
// Added BASE_URL and modified fetch requests as outlined in Step 2.

document.addEventListener("DOMContentLoaded", function () {
    const loginForm = document.getElementById("login-form");

    if (loginForm) {
        loginForm.addEventListener("submit", function (event) {
            event.preventDefault();
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

const BASE_URL = "https://ai-lab-test-l852otuc8-vabarcos-projects.vercel.app";

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
    if (!fileInput.files.length) {
        alert("Please select a file to upload.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const response = await fetch(`${BASE_URL}/analyze`, {
            method: "POST",
            body: formData,
        });
        const result = await response.json();
        if (result.error) throw new Error(result.error);
        checkStatus(result.task_id);
    } catch (error) {
        alert(`An error occurred: ${error.message}`);
    }
}

// ✅ Poll API to Check Analysis Status
async function checkStatus(taskId) {
    while (true) {
        try {
            const response = await fetch(`${BASE_URL}/analysis_status/${taskId}`);
            const result = await response.json();
            if (result.status?.includes("Processing")) {
                await new Promise(resolve => setTimeout(resolve, 5000));
            } else {
                document.getElementById("results").style.display = "block";
                document.getElementById("analysis-content").innerHTML = result.analysis ? 
                    `<div class="section-content">${result.analysis.replace(/\n/g, "<br>")}</div>` :
                    `<p style='color:red;'>Error: ${result.error}</p>`;
                break;
            }
        } catch (error) {
            console.error("Error checking status:", error);
            break;
        }
    }
}
