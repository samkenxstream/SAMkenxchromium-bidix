/**
 * Copyright 2022 Google LLC.
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {Protocol} from 'devtools-protocol';

import {CommonDataTypes, Script} from '../../../protocol/protocol.js';
import {BrowsingContextStorage} from '../context/browsingContextStorage.js';
import {CdpClient} from '../../CdpConnection.js';
import {IEventManager} from '../events/EventManager.js';
import {LogType, LoggerFn} from '../../../utils/log.js';

import {SHARED_ID_DIVIDER, ScriptEvaluator} from './scriptEvaluator.js';
import {RealmStorage} from './realmStorage.js';

export type RealmType = Script.RealmType;

export class Realm {
  readonly #realmStorage: RealmStorage;
  readonly #browsingContextStorage: BrowsingContextStorage;
  readonly #realmId: Script.Realm;
  readonly #browsingContextId: CommonDataTypes.BrowsingContext;
  readonly #executionContextId: Protocol.Runtime.ExecutionContextId;
  readonly #origin: string;
  readonly #type: RealmType;
  readonly #cdpClient: CdpClient;
  readonly #eventManager: IEventManager;
  readonly #scriptEvaluator: ScriptEvaluator;

  readonly sandbox?: string;
  readonly cdpSessionId: string;

  #logger?: LoggerFn;

  constructor(
    realmStorage: RealmStorage,
    browsingContextStorage: BrowsingContextStorage,
    realmId: Script.Realm,
    browsingContextId: CommonDataTypes.BrowsingContext,
    executionContextId: Protocol.Runtime.ExecutionContextId,
    origin: string,
    type: RealmType,
    sandbox: string | undefined,
    cdpSessionId: string,
    cdpClient: CdpClient,
    eventManager: IEventManager,
    logger?: LoggerFn
  ) {
    this.#realmId = realmId;
    this.#browsingContextId = browsingContextId;
    this.#executionContextId = executionContextId;
    this.sandbox = sandbox;
    this.#origin = origin;
    this.#type = type;
    this.cdpSessionId = cdpSessionId;
    this.#cdpClient = cdpClient;
    this.#realmStorage = realmStorage;
    this.#browsingContextStorage = browsingContextStorage;
    this.#eventManager = eventManager;
    this.#scriptEvaluator = new ScriptEvaluator(this.#eventManager);

    this.#realmStorage.realmMap.set(this.#realmId, this);

    this.#logger = logger;
  }

  async #releaseObject(handle: CommonDataTypes.Handle): Promise<void> {
    try {
      await this.cdpClient.sendCommand('Runtime.releaseObject', {
        objectId: handle,
      });
    } catch (e: any) {
      // Heuristic to determine if the problem is in the unknown handler.
      // Ignore the error if so.
      if (!(e.code === -32000 && e.message === 'Invalid remote object id')) {
        throw e;
      }
    }
  }

  async disown(handle: CommonDataTypes.Handle): Promise<void> {
    // Disowning an object from different realm does nothing.
    if (this.#realmStorage.knownHandlesToRealm.get(handle) !== this.realmId) {
      return;
    }

    await this.#releaseObject(handle);

    this.#realmStorage.knownHandlesToRealm.delete(handle);
  }

  cdpToBidiValue(
    cdpValue:
      | Protocol.Runtime.CallFunctionOnResponse
      | Protocol.Runtime.EvaluateResponse,
    resultOwnership: Script.ResultOwnership
  ): CommonDataTypes.RemoteValue {
    const deepSerializedValue = cdpValue.result.deepSerializedValue!;
    const bidiValue = this.deepSerializedToBiDi(deepSerializedValue);

    if (cdpValue.result.objectId) {
      const objectId = cdpValue.result.objectId;
      if (resultOwnership === 'root') {
        // Extend BiDi value with `handle` based on required `resultOwnership`
        // and  CDP response but not on the actual BiDi type.
        (bidiValue as any).handle = objectId;
        // Remember all the handles sent to client.
        this.#realmStorage.knownHandlesToRealm.set(objectId, this.realmId);
      } else {
        // No need in awaiting for the object to be released.
        void this.#releaseObject(objectId).catch((error) =>
          this.#logger?.(LogType.system, error)
        );
      }
    }

    return bidiValue;
  }

  deepSerializedToBiDi(
    webDriverValue: Protocol.Runtime.DeepSerializedValue
  ): CommonDataTypes.RemoteValue {
    // This relies on the CDP to implement proper BiDi serialization, except
    // backendNodeId/sharedId and `platformobject`.
    const result = webDriverValue as any;

    if (Object.hasOwn(result, 'weakLocalObjectReference')) {
      result.internalId = `${result.weakLocalObjectReference}`;
      delete result['weakLocalObjectReference'];
    }

    // Platform object is a special case. It should have only `{type: object}`
    // without `value` field.
    if (result.type === 'platformobject') {
      return {type: 'object'} as CommonDataTypes.RemoteValue;
    }

    const bidiValue = result.value;
    if (bidiValue === undefined) {
      return result;
    }

    if (result.type === 'node') {
      if (Object.hasOwn(bidiValue, 'backendNodeId')) {
        // eslint-disable-next-line @typescript-eslint/restrict-template-expressions
        result.sharedId = `${this.navigableId}${SHARED_ID_DIVIDER}${bidiValue.backendNodeId}`;
        delete bidiValue['backendNodeId'];
      }
      if (Object.hasOwn(bidiValue, 'children')) {
        for (const i in bidiValue.children) {
          bidiValue.children[i] = this.deepSerializedToBiDi(
            bidiValue.children[i]
          );
        }
      }
    }

    // Recursively update the nested values.
    if (['array', 'set'].includes(webDriverValue.type)) {
      for (const i in bidiValue) {
        bidiValue[i] = this.deepSerializedToBiDi(bidiValue[i]);
      }
    }
    if (['object', 'map'].includes(webDriverValue.type)) {
      for (const i in bidiValue) {
        bidiValue[i] = [
          this.deepSerializedToBiDi(bidiValue[i][0]),
          this.deepSerializedToBiDi(bidiValue[i][1]),
        ];
      }
    }

    return result;
  }

  toBiDi(): Script.RealmInfo {
    return {
      realm: this.realmId,
      origin: this.origin,
      type: this.type,
      context: this.browsingContextId,
      ...(this.sandbox === undefined ? {} : {sandbox: this.sandbox}),
    };
  }

  get realmId(): Script.Realm {
    return this.#realmId;
  }

  get navigableId(): string {
    return (
      this.#browsingContextStorage.findContext(this.#browsingContextId)
        ?.navigableId ?? 'UNKNOWN'
    );
  }

  get browsingContextId(): CommonDataTypes.BrowsingContext {
    return this.#browsingContextId;
  }

  get executionContextId(): Protocol.Runtime.ExecutionContextId {
    return this.#executionContextId;
  }

  get origin(): string {
    return this.#origin;
  }

  get type(): RealmType {
    return this.#type;
  }

  get cdpClient(): CdpClient {
    return this.#cdpClient;
  }

  async callFunction(
    functionDeclaration: string,
    _this: Script.ArgumentValue,
    _arguments: Script.ArgumentValue[],
    awaitPromise: boolean,
    resultOwnership: Script.ResultOwnership,
    serializationOptions: Script.SerializationOptions
  ): Promise<Script.CallFunctionResult> {
    const context = this.#browsingContextStorage.getContext(
      this.browsingContextId
    );
    await context.awaitUnblocked();

    return {
      result: await this.#scriptEvaluator.callFunction(
        this,
        functionDeclaration,
        _this,
        _arguments,
        awaitPromise,
        resultOwnership,
        serializationOptions
      ),
    };
  }

  async scriptEvaluate(
    expression: string,
    awaitPromise: boolean,
    resultOwnership: Script.ResultOwnership,
    serializationOptions: Script.SerializationOptions
  ): Promise<Script.EvaluateResult> {
    const context = this.#browsingContextStorage.getContext(
      this.browsingContextId
    );
    await context.awaitUnblocked();

    return {
      result: await this.#scriptEvaluator.scriptEvaluate(
        this,
        expression,
        awaitPromise,
        resultOwnership,
        serializationOptions
      ),
    };
  }

  /**
   * Serializes a given CDP object into BiDi, keeping references in the
   * target's `globalThis`.
   * @param cdpObject CDP remote object to be serialized.
   * @param resultOwnership Indicates desired ResultOwnership.
   */
  async serializeCdpObject(
    cdpObject: Protocol.Runtime.RemoteObject,
    resultOwnership: Script.ResultOwnership
  ): Promise<CommonDataTypes.RemoteValue> {
    return this.#scriptEvaluator.serializeCdpObject(
      cdpObject,
      resultOwnership,
      this
    );
  }

  /**
   * Gets the string representation of an object. This is equivalent to
   * calling toString() on the object value.
   * @param cdpObject CDP remote object representing an object.
   * @return string The stringified object.
   */
  async stringifyObject(
    cdpObject: Protocol.Runtime.RemoteObject
  ): Promise<string> {
    return ScriptEvaluator.stringifyObject(cdpObject, this);
  }
}
