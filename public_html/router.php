<?php
declare(strict_types=1);

/**
 * PHP yerleşik sunucu yönlendiricisi — uploads altında PHP çalıştırmayı engeller.
 * Kullanım: php -S localhost:8080 -t public_html public_html/router.php
 */

$uri = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

if (preg_match('#^/assets/img/uploads/.+\.php$#i', $uri)) {
    http_response_code(403);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Forbidden';
    return true;
}

if ($uri === '/admin') {
    header('Location: /admin/', true, 301);
    return true;
}

$fsPath = __DIR__ . $uri;

if ($uri !== '/') {
    $dirPath = is_dir($fsPath) ? $fsPath : null;
    if ($dirPath === null && str_ends_with($uri, '/')) {
        $trimmed = rtrim($fsPath, '/\\');
        if (is_dir($trimmed)) {
            $dirPath = $trimmed;
        }
    }
    if ($dirPath !== null) {
        $index = $dirPath . DIRECTORY_SEPARATOR . 'index.php';
        if (is_file($index)) {
            require $index;
            return true;
        }
    }
}

if ($uri !== '/' && is_file($fsPath)) {
    return false;
}

if ($uri === '/' && is_file(__DIR__ . '/index.php')) {
    require __DIR__ . '/index.php';
    return true;
}

http_response_code(404);
echo 'Not Found';
return true;
