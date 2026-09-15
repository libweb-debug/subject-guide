document.addEventListener("DOMContentLoaded", function () {
    const accordionItems = document.querySelectorAll(
        ".guide-accordion-item"
    );

    const searchInput = document.getElementById("guide-search");
    const emptyMessage = document.getElementById("guide-search-empty");

    accordionItems.forEach(function (item) {
        const button = item.querySelector(
            ".guide-accordion-button"
        );

        button.addEventListener("click", function () {
            const isOpen = item.classList.toggle("open");

            button.setAttribute(
                "aria-expanded",
                isOpen ? "true" : "false"
            );
        });
    });

    searchInput.addEventListener("input", function () {
        const keyword = searchInput.value
            .trim()
            .toLowerCase();

        let totalVisible = 0;

        accordionItems.forEach(function (item) {
            const departmentLinks = item.querySelectorAll(
                ".guide-department-link"
            );

            let visibleInCollege = 0;

            departmentLinks.forEach(function (link) {
                const departmentName =
                    link.dataset.departmentName.toLowerCase();

                const matched =
                    keyword === "" ||
                    departmentName.includes(keyword);

                link.hidden = !matched;

                if (matched) {
                    visibleInCollege++;
                    totalVisible++;
                }
            });

            if (keyword === "") {
                item.hidden = false;
                return;
            }

            item.hidden = visibleInCollege === 0;

            if (visibleInCollege > 0) {
                item.classList.add("open");

                item.querySelector(
                    ".guide-accordion-button"
                ).setAttribute(
                    "aria-expanded",
                    "true"
                );
            }
        });

        emptyMessage.hidden =
            keyword === "" || totalVisible > 0;
    });
});