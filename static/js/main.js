document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("certificate_file");
    const dropzone = document.getElementById("dropzone");
    const selectedCard = document.getElementById("selected-file-card");
    const fileName = document.getElementById("selected-file-name");
    const fileSize = document.getElementById("selected-file-size");
    const removeButton = document.getElementById("remove-file-button");
    const verifyButton = document.getElementById("verify-button");

    if (!fileInput || !dropzone) {
        return;
    }

    function formatSize(bytes) {
        if (bytes < 1024 * 1024) {
            return `${(bytes / 1024).toFixed(1)} KB`;
        }

        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    }

    function selectFile(file) {
        fileName.textContent = file.name;
        fileSize.textContent = formatSize(file.size);

        selectedCard.classList.add("active");
        dropzone.classList.add("file-ready");

        verifyButton.disabled = false;
    }

    function resetFile() {
        fileInput.value = "";

        fileName.textContent = "No file selected";
        fileSize.textContent = "";

        selectedCard.classList.remove("active");
        dropzone.classList.remove("file-ready");

        verifyButton.disabled = true;
    }

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            selectFile(fileInput.files[0]);
        }
    });

    removeButton?.addEventListener("click", resetFile);

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.add("drag-over");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.remove("drag-over");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        const files = event.dataTransfer.files;

        if (files.length > 0) {
            fileInput.files = files;
            selectFile(files[0]);
        }
    });
});