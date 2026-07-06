<?php
declare(strict_types=1);

/**
 * İletişim formu API taslağı.
 * POST: name, email, message
 */

header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Yalnızca POST istekleri kabul edilir.'], JSON_UNESCAPED_UNICODE);
    exit;
}

$name = trim((string) ($_POST['name'] ?? ''));
$email = trim((string) ($_POST['email'] ?? ''));
$message = trim((string) ($_POST['message'] ?? ''));

if ($name === '' || $email === '' || $message === '') {
    http_response_code(422);
    echo json_encode(['ok' => false, 'error' => 'Tüm alanlar zorunludur.'], JSON_UNESCAPED_UNICODE);
    exit;
}

if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    http_response_code(422);
    echo json_encode(['ok' => false, 'error' => 'Geçerli bir e-posta adresi girin.'], JSON_UNESCAPED_UNICODE);
    exit;
}

// TODO: E-posta gönderimi veya veritabanı kaydı burada yapılacak.
echo json_encode([
    'ok' => true,
    'message' => 'Mesajınız alındı. (Taslak — henüz gönderilmedi.)',
], JSON_UNESCAPED_UNICODE);
