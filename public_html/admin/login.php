<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/admin_auth.php';

if (admin_is_logged_in()) {
    header('Location: /admin/dashboard.php', true, 302);
    exit;
}

$error = '';
$locked = admin_is_locked_out();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!admin_verify_csrf($_POST['csrf_token'] ?? null)) {
        admin_csrf_fail();
    }

    $password = (string) ($_POST['password'] ?? '');
    if ($locked) {
        $error = 'Çok fazla başarısız deneme. Lütfen birkaç dakika sonra tekrar deneyin.';
    } elseif (admin_attempt_login($password)) {
        header('Location: /admin/dashboard.php', true, 302);
        exit;
    } else {
        $error = 'Geçersiz şifre.';
        $locked = admin_is_locked_out();
    }
}

$csrf = admin_csrf_token();
?>
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Giriş — Emirgan Danışmanlık</title>
    <link rel="stylesheet" href="/admin/assets/admin.css">
</head>
<body class="admin-login-page">
    <main class="admin-login-card">
        <h1>Yönetim Paneli</h1>
        <p class="admin-muted">Emirgan Danışmanlık içerik yönetimi</p>
        <?php if ($error !== ''): ?>
            <p class="admin-alert admin-alert--error" role="alert"><?= e($error) ?></p>
        <?php endif; ?>
        <form method="post" class="admin-form">
            <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
            <label for="password">Şifre</label>
            <input type="password" id="password" name="password" required autocomplete="current-password" <?= $locked ? 'disabled' : '' ?>>
            <button type="submit" class="admin-btn admin-btn--primary" <?= $locked ? 'disabled' : '' ?>>Giriş Yap</button>
        </form>
        <p class="admin-footer-link"><a href="/">← Siteye dön</a></p>
    </main>
</body>
</html>
