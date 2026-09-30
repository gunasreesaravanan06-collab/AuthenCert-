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

    function formatFileSize(bytes) {
        if (bytes < 1024 * 1024) {
            return `${(bytes / 1024).toFixed(1)} KB`;
        }

        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    }

    function showSelectedFile(file) {
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);

        selectedCard.classList.add("active");
        verifyButton.disabled = false;
        dropzone.classList.add("has-file");
    }

    function resetSelectedFile() {
        fileInput.value = "";
        fileName.textContent = "No file selected";
        fileSize.textContent = "";

        selectedCard.classList.remove("active");
        verifyButton.disabled = true;
        dropzone.classList.remove("has-file");
    }

    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            showSelectedFile(fileInput.files[0]);
        }
    });

    removeButton?.addEventListener("click", () => {
        resetSelectedFile();
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.add("drag-active");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropzone.classList.remove("drag-active");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        const files = event.dataTransfer.files;

        if (files.length > 0) {
            fileInput.files = files;
            showSelectedFile(files[0]);
        }
    });
});