#### didList:
1. 把页面改成可交互网站：输入房间号，点击生成建议。
2. 后端接入真实接口流程：先 GET /api/coach/snapshot/<room_code>，再 POST /api/coach/evaluate_move 验证候选，不合法就继续生成直到合法。
3. 输出结果符合 worksheet 要求的 JSON 字段：position、value、reason、confidence、risk，并附带快照摘要与尝试过程。
4. 自动读取 game_coach_game/game_data.json 中账号密码，按当前回合玩家登录后进行 evaluate_move，避免会话不匹配。

#### 收获
1. 对这些架构之类的逐渐熟练：）
2. 我再也不会忘记接Ollama了 为什么要忘记接Ollama啊我问你