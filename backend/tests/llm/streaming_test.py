"""
LLM 流式响应测试 - 使用 OkHttp 验证 chunk 接收时间差
"""
import okhttp3
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import java.util.concurrent.TimeUnit

class LlmStreamingTest {

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val baseUrl = "http://localhost:8000"
    private val apiKey = "your-api-key"

    /**
     * 测试流式响应 - 打印每个 chunk 的接收时间和内容
     */
    @Test
    fun `test streaming response chunk timing`() = runBlocking {
        val startTime = System.currentTimeMillis()

        // 构建请求
        val request = Request.Builder()
            .url("$baseUrl/api/v1/model-gateway/chat/completions")
            .addHeader("Content-Type", "application/json")
            .addHeader("Authorization", "Bearer $apiKey")
            .post(
                """
                {
                    "model_type": "llm",
                    "messages": [
                        {"role": "user", "content": "请用 100 字介绍人工智能"}
                    ],
                    "temperature": 0.7,
                    "stream": true
                }
                """.trimIndent().toRequestBody(MediaType.parse("application/json"))
            )
            .build()

        // 执行请求并处理 SSE 流
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                println("请求失败：${e.message}")
            }

            override fun onResponse(call: Call, response: Response) {
                response.body?.byteStream()?.use { inputStream ->
                    val reader = inputStream.bufferedReader()
                    var lineCount = 0
                    var lastChunkTime = 0L

                    reader.useLines { lines ->
                        lines.forEach { line ->
                            val currentTime = System.currentTimeMillis()
                            val elapsedSinceStart = currentTime - startTime
                            val elapsedSinceLastChunk = if (lastChunkTime > 0) {
                                currentTime - lastChunkTime
                            } else {
                                0L
                            }
                            lastChunkTime = currentTime
                            lineCount++

                            // 只打印 SSE 数据行
                            if (line.startsWith("data: ")) {
                                val data = line.substring(6)
                                if (data != "[DONE]") {
                                    println("[$lineCount] +${elapsedSinceLastChunk}ms (总计：${elapsedSinceStart}ms): $data")
                                } else {
                                    println("[$lineCount] +${elapsedSinceLastChunk}ms (总计：${elapsedSinceStart}ms): [DONE]")
                                }
                            }
                        }
                    }
                }
            }
        })

        // 等待请求完成
        delay(60000)
    }

    /**
     * 测试流式响应 - 使用 OkHttp 的 EventSource (SSE 支持)
     */
    @Test
    fun `test streaming with EventSource`() = runBlocking {
        val startTime = System.currentTimeMillis()
        val chunkTimes = mutableListOf<Long>()

        // 使用 OkHttp 的 EventSource 来处理 SSE
        val eventSourceFactory = EventSources.createFactory(client)

        val request = Request.Builder()
            .url("$baseUrl/api/v1/model-gateway/chat/completions")
            .addHeader("Content-Type", "application/json")
            .addHeader("Authorization", "Bearer $apiKey")
            .post(
                """
                {
                    "model_type": "llm",
                    "messages": [
                        {"role": "user", "content": "请用 100 字介绍人工智能"}
                    ],
                    "temperature": 0.7,
                    "stream": true
                }
                """.trimIndent().toRequestBody(MediaType.parse("application/json"))
            )
            .build()

        val eventSourceListener = object : EventSourceListener() {
            override fun onOpen(eventSource: EventSource, response: Response) {
                println("SSE 连接已建立")
            }

            override fun onEvent(
                eventSource: EventSource,
                id: String?,
                type: String?,
                data: String
            ) {
                val currentTime = System.currentTimeMillis()
                val elapsedSinceStart = currentTime - startTime
                val lastTime = chunkTimes.lastOrNull() ?: startTime
                val elapsedSinceLastChunk = currentTime - lastTime
                chunkTimes.add(currentTime)

                if (data != "[DONE]") {
                    println("Chunk +${elapsedSinceLastChunk}ms (总计：${elapsedSinceStart}ms): $data")
                } else {
                    println("[DONE] +${elapsedSinceLastChunk}ms (总计：${elapsedSinceStart}ms)")

                    // 打印统计信息
                    println("\n========== 统计信息 ==========")
                    println("总 chunk 数：${chunkTimes.size}")
                    println("总耗时：${elapsedSinceStart}ms")
                    if (chunkTimes.size > 1) {
                        val avgInterval = elapsedSinceStart.toDouble() / (chunkTimes.size - 1)
                        println("平均 chunk 间隔：${String.format("%.2f", avgInterval)}ms")
                    }
                }
            }

            override fun onFailure(
                eventSource: EventSource,
                t: Throwable?,
                response: Response?
            ) {
                println("SSE 错误：${t?.message ?: response?.message}")
            }

            override fun onClosed(eventSource: EventSource) {
                println("SSE 连接已关闭")
            }
        }

        eventSourceFactory.newEventSource(request, eventSourceListener)

        // 等待请求完成
        delay(60000)
    }

    /**
     * 同步方式测试流式响应
     */
    @Test
    fun `test streaming response sync`() {
        val startTime = System.currentTimeMillis()
        val chunkTimes = mutableListOf<Long>()

        val request = Request.Builder()
            .url("$baseUrl/api/v1/model-gateway/chat/completions")
            .addHeader("Content-Type", "application/json")
            .addHeader("Authorization", "Bearer $apiKey")
            .post(
                """
                {
                    "model_type": "llm",
                    "messages": [
                        {"role": "user", "content": "请用 100 字介绍人工智能"}
                    ],
                    "temperature": 0.7,
                    "stream": true
                }
                """.trimIndent().toRequestBody(MediaType.parse("application/json"))
            )
            .build()

        val response = client.newCall(request).execute()

        if (!response.isSuccessful) {
            println("请求失败：${response.code} - ${response.message}")
            return
        }

        response.body?.byteStream()?.use { inputStream ->
            val reader = inputStream.bufferedReader()
            var lineCount = 0
            var lastChunkTime = startTime

            reader.useLines { lines ->
                lines.forEach { line ->
                    val currentTime = System.currentTimeMillis()

                    if (line.startsWith("data: ")) {
                        val data = line.substring(6)
                        val elapsedSinceLastChunk = currentTime - lastChunkTime

                        if (data != "[DONE]") {
                            println("Chunk $lineCount: +${elapsedSinceLastChunk}ms | $data")
                        } else {
                            println("Chunk $lineCount: +${elapsedSinceLastChunk}ms | [DONE]")
                        }

                        lastChunkTime = currentTime
                        chunkTimes.add(currentTime)
                        lineCount++
                    }
                }
            }
        }

        // 打印统计信息
        val totalTime = System.currentTimeMillis() - startTime
        println("\n========== 统计信息 ==========")
        println("总 chunk 数：${chunkTimes.size}")
        println("总耗时：${totalTime}ms")
        if (chunkTimes.size > 1) {
            val avgInterval = totalTime.toDouble() / (chunkTimes.size - 1)
            println("平均 chunk 间隔：${String.format("%.2f", avgInterval)}ms")
            println("最小间隔：${chunkTimes.zipWithNext { a, b -> b - a }.minOrNull()}ms")
            println("最大间隔：${chunkTimes.zipWithNext { a, b -> b - a }.maxOrNull()}ms")
        }
    }
}
