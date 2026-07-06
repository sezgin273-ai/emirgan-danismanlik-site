<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/admin_auth.php';

if (admin_is_logged_in()) {
    header('Location: /admin/dashboard.php', true, 302);
    exit;
}

header('Location: /admin/login.php', true, 302);
